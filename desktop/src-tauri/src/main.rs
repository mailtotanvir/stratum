use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use rfd::MessageDialog;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const STRATUM_BACKEND_MODE: &str = "tauri";
const BACKEND_LOCK_PATH: &str = "/tmp/stratum_backend.lock";
const HEALTH_URL: &str = "http://127.0.0.1:8000/health";
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 8000;

struct BackendProcess(Mutex<Option<Child>>);

impl BackendProcess {
    fn stop(&self) {
        let mut guard = self.0.lock().expect("backend process lock poisoned");
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn main() {
    let context = tauri::generate_context!();

    println!("Stratum Backend Ownership Mode: TAURI");

    let app = tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let backend_running = backend_ready()?;
            println!("Backend already running: {backend_running}");

            let backend_spawned = if backend_running {
                false
            } else {
                if lock_exists() {
                    println!("Backend ownership lock already held externally. Attaching without spawning.");
                    true
                } else {
                    create_lock()?;
                    let mut backend = launch_backend()?;
                    if let Err(error) = wait_for_backend_ready(&mut backend, Duration::from_secs(60)) {
                        terminate_child(&mut backend);
                        remove_lock();
                        show_startup_error(
                            "Backend startup failed",
                            &format!("The FastAPI backend could not be started: {error}"),
                        );
                        std::process::exit(1);
                    }
                    let state = app.state::<BackendProcess>();
                    let mut guard = state.0.lock().expect("backend process lock poisoned");
                    *guard = Some(backend);
                    false
                }
            };

            println!("Backend spawned by this process: {backend_spawned}");

            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Stratum Desktop")
                .build();

            match window {
                Ok(window) => {
                    if let Err(error) = window.show() {
                        app.state::<BackendProcess>().stop();
                        return Err(Box::new(error));
                    }
                }
                Err(error) => {
                    app.state::<BackendProcess>().stop();
                    return Err(Box::new(error));
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                window.app_handle().state::<BackendProcess>().stop();
            }
        })
        .build(context)
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. }) {
            app_handle.state::<BackendProcess>().stop();
            remove_lock();
        }
    });
}

fn launch_backend() -> io::Result<Child> {
    let backend_dir = backend_dir()?;
    let mut command = Command::new("uv");
    command
        .current_dir(backend_dir)
        .args([
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            &BACKEND_PORT.to_string(),
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());
    command.spawn()
}

fn backend_lock_path() -> PathBuf {
    Path::new(BACKEND_LOCK_PATH).to_path_buf()
}

fn lock_exists() -> bool {
    backend_lock_path().exists()
}

fn create_lock() -> io::Result<()> {
    let lock_path = backend_lock_path();
    let mut file = OpenOptions::new().write(true).create_new(true).open(&lock_path)?;
    writeln!(file, "{}", std::process::id())?;
    Ok(())
}

fn remove_lock() {
    let _ = fs::remove_file(backend_lock_path());
}

fn backend_dir() -> io::Result<std::path::PathBuf> {
    let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|desktop_dir| desktop_dir.parent())
        .map(|repo_root| repo_root.join("backend"))
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "backend directory not found"))
}

fn backend_ready() -> io::Result<bool> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(io::Error::other)?;

    match client.get(HEALTH_URL).send() {
        Ok(response) if response.status().is_success() => Ok(true),
        _ => Ok(false),
    }
}

fn wait_for_backend_ready(backend: &mut Child, timeout: Duration) -> io::Result<()> {
    let deadline = Instant::now() + timeout;
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(io::Error::other)?;

    loop {
        if Instant::now() > deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "The FastAPI backend did not become healthy within 60 seconds",
            ));
        }

        if let Some(status) = backend.try_wait()? {
            return Err(io::Error::new(
                io::ErrorKind::Other,
                format!("The FastAPI backend exited before it became ready with status {status}"),
            ));
        }

        match client.get(HEALTH_URL).send() {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(_) | Err(_) => thread::sleep(Duration::from_millis(500)),
        }
    }
}

fn terminate_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

fn show_startup_error(title: &str, message: &str) {
    let _ = MessageDialog::new()
        .set_title(title)
        .set_description(message)
        .set_buttons(rfd::MessageButtons::Ok)
        .show();
}
