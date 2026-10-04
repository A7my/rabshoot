use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, RunEvent, WindowEvent};
use tauri_plugin_autostart::MacosLauncher;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Clone, Serialize)]
struct EngineInfo {
    port: u16,
    token: String,
}

#[derive(Default)]
struct EngineState {
    info: Mutex<Option<EngineInfo>>,
    child: Mutex<Option<CommandChild>>,
    quitting: Mutex<bool>,
}

/// Port and token of the local engine API; waits for the sidecar to be ready.
#[tauri::command]
async fn engine_info(state: tauri::State<'_, EngineState>) -> Result<EngineInfo, String> {
    for _ in 0..600 {
        if let Some(info) = state.info.lock().unwrap().clone() {
            return Ok(info);
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    Err("The RabShoot engine did not start".into())
}

fn spawn_engine(app: &AppHandle) -> Result<(), String> {
    let command = app
        .shell()
        .sidecar("rabshoot-engine")
        .map_err(|e| e.to_string())?
        .args(["serve", "--watch-stdin"]);
    let (mut rx, child) = command.spawn().map_err(|e| e.to_string())?;
    {
        let state = app.state::<EngineState>();
        *state.info.lock().unwrap() = None;
        *state.child.lock().unwrap() = Some(child);
    }

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let text = String::from_utf8_lossy(&line);
                    if let Ok(value) = serde_json::from_str::<serde_json::Value>(text.trim()) {
                        if value["event"] == "ready" {
                            let info = EngineInfo {
                                port: value["port"].as_u64().unwrap_or(0) as u16,
                                token: value["token"].as_str().unwrap_or_default().to_string(),
                            };
                            *handle.state::<EngineState>().info.lock().unwrap() = Some(info);
                            let _ = handle.emit("engine-ready", ());
                        }
                    }
                }
                CommandEvent::Stderr(line) => {
                    #[cfg(debug_assertions)]
                    eprintln!("[engine] {}", String::from_utf8_lossy(&line).trim_end());
                    #[cfg(not(debug_assertions))]
                    let _ = line;
                }
                CommandEvent::Terminated(_) => {
                    let quitting = {
                        let state = handle.state::<EngineState>();
                        *state.info.lock().unwrap() = None;
                        *state.child.lock().unwrap() = None;
                        let q = *state.quitting.lock().unwrap();
                        q
                    };
                    if !quitting {
                        tokio::time::sleep(Duration::from_secs(2)).await;
                        if let Err(err) = spawn_engine(&handle) {
                            eprintln!("Failed to restart the engine: {err}");
                        }
                    }
                    break;
                }
                _ => {}
            }
        }
    });
    Ok(())
}

fn stop_engine(app: &AppHandle) {
    let state = app.state::<EngineState>();
    *state.quitting.lock().unwrap() = true;
    let child = state.child.lock().unwrap().take();
    if let Some(child) = child {
        let _ = child.kill();
    }
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open RabShoot", true, None::<&str>)?;
    let pause = MenuItem::with_id(app, "pause", "Pause / resume all reports", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit RabShoot", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &pause, &separator, &quit])?;

    let mut tray = TrayIconBuilder::with_id("main")
        .tooltip("RabShoot")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main(app),
            "pause" => {
                let _ = app.emit("tray-toggle-pause", ());
            }
            "quit" => {
                stop_engine(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![engine_info])
        .setup(|app| {
            let handle = app.handle().clone();
            if let Err(err) = spawn_engine(&handle) {
                eprintln!("Failed to start the engine: {err}");
            }
            build_tray(&handle)?;
            #[cfg(unix)]
            {
                // GTK ignores SIGTERM; logout/shutdown and `kill` must still stop the engine.
                let handle = handle.clone();
                tauri::async_runtime::spawn(async move {
                    use tokio::signal::unix::{signal, SignalKind};
                    let (Ok(mut term), Ok(mut int)) =
                        (signal(SignalKind::terminate()), signal(SignalKind::interrupt()))
                    else {
                        return;
                    };
                    tokio::select! {
                        _ = term.recv() => {}
                        _ = int.recv() => {}
                    }
                    stop_engine(&handle);
                    handle.exit(0);
                });
            }
            let minimized = std::env::args().any(|a| a == "--minimized");
            if !minimized {
                show_main(&handle);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the window keeps RabShoot running in the tray so reports still go out.
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building RabShoot");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_engine(handle);
        }
    });
}
