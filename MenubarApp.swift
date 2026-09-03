import Cocoa
import Foundation

class ScreenpipeManager: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var timer: Timer?
    var isRunning = false
    var meetingDetected = false

    let screenpipeBin = "/Users/acyclic/build/screenpipe/target/release/screenpipe"
    let screenpipePort = "3030"
    let dashboardURL = "http://localhost:7654"

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        
        // Create eye icon as NSImage (template)
        let eyeImage = createEyeImage()
        statusItem.button?.image = eyeImage
        statusItem.button?.image?.isTemplate = true
        statusItem.button?.title = ""

        let menu = NSMenu()
        menu.addItem(withTitle: "Start Recording", action: #selector(startRecording), keyEquivalent: "s")
        menu.addItem(withTitle: "Stop Recording", action: #selector(stopRecording), keyEquivalent: "x")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "d")
        menu.addItem(NSMenuItem.separator())
        let statusMenuItem = NSMenuItem(title: "Status: Checking...", action: nil, keyEquivalent: "")
        statusMenuItem.tag = 100
        menu.addItem(statusMenuItem)
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Quit", action: #selector(quitApp), keyEquivalent: "q")

        statusItem.menu = menu

        // Start web server in background
        startWebServer()

        // Start status timer
        timer = Timer.scheduledTimer(timeInterval: 5.0, target: self, selector: #selector(refreshStatus), userInfo: nil, repeats: true)
        
        // Auto-start screenpipe on launch
        startRecording()
        
        refreshStatus()
    }

    func createEyeImage() -> NSImage {
        let size = NSSize(width: 20, height: 16)
        let image = NSImage(size: size)
        image.lockFocus()
        
        let path = NSBezierPath()
        // Eye outline (almond shape)
        let rect = NSRect(x: 1, y: 2, width: 18, height: 12)
        path.appendOval(in: rect)
        
        // Iris/pupil
        let pupilRect = NSRect(x: 7, y: 4, width: 6, height: 6)
        NSBezierPath(ovalIn: pupilRect).fill()
        
        // Fill outline as stroke
        let lineWidth: CGFloat = 2.0
        path.lineWidth = lineWidth
        path.stroke()
        
        image.unlockFocus()
        return image
    }

    func startWebServer() {
        let task = Process()
        task.launchPath = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
        let serverPath = "/Users/acyclic/build/screenpipe-manager/server.py"
        task.arguments = [serverPath]
        task.launch()
    }

    @objc func startRecording() {
        // Check if already running to avoid duplicates
        if checkScreenpipeRunning() {
            print("[Screenpipe] Already running")
            return
        }
        let task = Process()
        task.launchPath = "/bin/bash"
        task.arguments = ["-c", "nohup \(screenpipeBin) record --port \(screenpipePort) --language english > /tmp/screenpipe.log 2>&1 &"]
        task.launch()
        print("[Screenpipe] Recording started")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { self.refreshStatus() }
    }

    @objc func stopRecording() {
        let task = Process()
        task.launchPath = "/bin/bash"
        task.arguments = ["-c", "pkill -f 'screenpipe record'"]
        task.launch()
        print("[Screenpipe] Recording stopped")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.refreshStatus() }
    }

    @objc func openDashboard() {
        NSWorkspace.shared.open(URL(string: dashboardURL)!)
    }

    @objc func quitApp() {
        timer?.invalidate()
        NSApplication.shared.terminate(self)
    }

    @objc func refreshStatus() {
        let running = checkScreenpipeRunning()
        isRunning = running

        if let menu = statusItem.menu {
            if let statusItem2 = menu.item(withTag: 100) {
                if running {
                    let health = checkHealth()
                    let meeting = health?["meeting"] as? Bool ?? false
                    meetingDetected = meeting
                    if meeting {
                        statusItem2.title = "Status: Recording (Meeting active)"
                    } else {
                        statusItem2.title = "Status: Recording"
                    }
                } else {
                    statusItem2.title = "Status: Stopped"
                }
            }

            menu.item(at: 0)?.isEnabled = !running
            menu.item(at: 1)?.isEnabled = running
        }
    }

    func checkScreenpipeRunning() -> Bool {
        let task = Process()
        task.launchPath = "/usr/bin/pgrep"
        task.arguments = ["-f", "screenpipe record"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.launch()
        task.waitUntilExit()
        return task.terminationStatus == 0
    }

    func checkHealth() -> [String: Any]? {
        guard let url = URL(string: "http://localhost:\(screenpipePort)/health") else { return nil }
        guard let data = try? Data(contentsOf: url) else { return nil }
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let audio = json["audio_pipeline"] as? [String: Any] {
            return ["meeting": audio["meeting_detected"] ?? false]
        }
        return nil
    }
}

let app = NSApplication.shared
let delegate = ScreenpipeManager()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
