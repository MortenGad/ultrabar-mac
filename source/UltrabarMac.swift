import SwiftUI
import AppKit

final class Model: ObservableObject {
 @Published var macConfig=MacButtonConfig() { didSet { macDirty=true } }
 @Published var macDirty=false
 @Published var macEnabled=false
 @Published var macEvent="No Mac button presses received yet."
 @Published var macReview:[String:Any]=[:]
 @Published var showMacReview=false
 var macLoaded=false

 @Published var widgetDocument = WidgetDocument.empty() { didSet { widgetDirty = true } }
 @Published var widgetDirty = false
 @Published var widgetSelection: String? = nil
 @Published var widgetSounds: [[String:Any]] = []
 @Published var widgetApps: [[String:Any]] = []
 @Published var widgetReview: [String:Any] = [:]
 @Published var showWidgetReview = false
 var exportRequested = false
 var startupPending = true
 @Published var host = ""
 @Published var connected = false
 @Published var busy = false
 @Published var message = "Connect to your Ultrabar to begin."
 @Published var modules: [[String:Any]] = []
 @Published var profiles: [[String:Any]] = []
 @Published var selectedProfile = "default"
 @Published var wallpaperImage: NSImage?
 @Published var wallpaperData: Data?
 @Published var wallpaperName = "No image selected"
 @Published var screenEnabled = false
 @Published var screenTime = "TIME_5MIN"
 @Published var screenSaved = false
 @Published var bridgeOn = false
 @Published var profileName = "Mac Volume"
 @Published var draftText = ""
 @Published var showReview = false
 @Published var volumeText = "Waiting for knob input"
 @Published var error = false
 private var process: Process?
 private var stdinPipe: Pipe?
 private var buffer = Data()
 func start() {
  guard process == nil else { return }
  let p = Process(), input = Pipe(), output = Pipe(), errors = Pipe()
  p.executableURL = URL(fileURLWithPath: "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3")
  guard let script = Bundle.main.path(forResource: "bridge", ofType: "py") else { message = "Missing device bridge."; error = true; return }
  p.arguments = ["-u", script]; p.standardInput = input; p.standardOutput = output; p.standardError = errors
  output.fileHandleForReading.readabilityHandler = { [weak self] handle in
   let d = handle.availableData
   if !d.isEmpty { DispatchQueue.main.async { self?.consume(d) } }
  }
  p.terminationHandler = { [weak self] _ in DispatchQueue.main.async { self?.connected = false; self?.busy = false; self?.message = "Device bridge stopped. Reopen the app to reconnect." } }
  do { try p.run(); process = p; stdinPipe = input }
  catch { message = "Python 3.14 could not start: \(error.localizedDescription)"; self.error = true }
 }
 func consume(_ data: Data) {
  buffer.append(data)
  while let range = buffer.range(of: Data([10])) {
   let line = buffer.subdata(in: 0..<range.lowerBound); buffer.removeSubrange(0..<range.upperBound)
   guard let o = try? JSONSerialization.jsonObject(with: line) as? [String:Any] else { continue }
   if let event = o["event"] as? String {
    if event == "mac_action" { macEvent=o["message"] as? String ?? "App launched" }
    else if event == "volume" { volumeText = "Mac volume: \(o["value"] ?? "—")%" }
    else if event == "disconnected" { connected = false; bridgeOn = false; message = o["message"] as? String ?? "Disconnected" }
    else { message = o["message"] as? String ?? message }
    continue
   }
   busy = false
   guard o["ok"] as? Bool == true else { exportRequested = false; error = true; message = o["message"] as? String ?? "Request failed"; continue }
   error = false
   let op = o["op"] as? String ?? ""
   let r = o["result"]
   switch op {
   case "connect", "pair", "refresh":
    guard let d = r as? [String:Any] else { continue }
    connected = true; modules = d["modules"] as? [[String:Any]] ?? []; profiles = d["profiles"] as? [[String:Any]] ?? []; widgetApps = d["widgetApps"] as? [[String:Any]] ?? []
    if !profiles.contains(where: { $0["value"] as? String == selectedProfile }) { selectedProfile = profiles.first?["value"] as? String ?? "" }
    if let screen = d["screen"] as? [String:Any] {
     screenEnabled = screen["featureEnabled"] as? Bool ?? false; screenTime = screen["lockTime"] as? String ?? "TIME_5MIN"; screenSaved = true
    } else { screenSaved = false }
    message = "Connected securely. Your Mac is authorised."
    if op == "connect" || op == "pair" { DispatchQueue.main.async { self.send("scan") } }
   case "actions_load":
    if let r=r { loadMacButtons(r);macEnabled=(r as? [String:Any])?["enabled"] as? Bool ?? false };macLoaded=true;message="Mac button configuration loaded."
   case "actions_save":
    if let r=r { loadMacButtons(r) };message="App launchers saved locally."
   case "actions_review":
    macReview=r as? [String:Any] ?? [:];showMacReview=true
   case "actions_deploy":
    macDirty=false;macEnabled=true
    if let d=r as? [String:Any] { profiles=d["profiles"] as? [[String:Any]] ?? [];selectedProfile=d["profileId"] as? String ?? "";message=d["message"] as? String ?? "Applied" }
   case "actions_test": message=r as? String ?? "App launched"
   case "actions_enabled": message=macEnabled ? "Mac app buttons enabled." : "Mac app buttons paused."
   case "widget_sounds":
    widgetSounds=r as? [[String:Any]] ?? [];message="Found \(widgetSounds.count) installed soundscapes."
   case "widget_load":
    if let d = r as? [String:Any], let doc=d["document"] { loadWidgetDocument(doc); widgetDirty = !(d["saved"] as? Bool ?? false) }
    message = widgetDirty ? "New example layout. It is not a copy of the device’s current widgets." : "Saved local layout opened."
    if startupPending { startupPending=false; DispatchQueue.main.async { if self.host.isEmpty { self.send("actions_load") } else { self.send("connect",["host":self.host]) } } }
   case "widget_validate":
    if let r=r {
     if exportRequested { exportRequested=false; exportWidgetDocument(r) }
     else { loadWidgetDocument(r); widgetDirty=true; message="Layout opened. Save draft to keep it locally." }
    }
   case "widget_save":
    widgetDirty=false; message="Widget draft saved on this Mac. The Ultrabar has not been changed."
   case "widget_review":
    widgetReview=r as? [String:Any] ?? [:]; showWidgetReview=true; message="Review the widget layout before applying."
   case "widget_deploy":
    if let d=r as? [String:Any] { profiles=d["profiles"] as? [[String:Any]] ?? []; selectedProfile=d["profileId"] as? String ?? selectedProfile; message=d["message"] as? String ?? "Layout saved." }
    widgetDirty=false
   case "scan": modules = r as? [[String:Any]] ?? []; message = "Listed \(modules.count) modules from scan and device status."; if !macLoaded { DispatchQueue.main.async { self.send("actions_load") } }
   case "wallpaper_show": message=r as? String ?? "Image sent."
   case "screen": screenSaved = true; message = "Screen settings saved and verified on the Ultrabar."
   case "switch": message = "Profile switched."
   case "draft":
    if let r = r, let data = try? JSONSerialization.data(withJSONObject:r,options:[.prettyPrinted,.sortedKeys]) { draftText = String(data:data,encoding:.utf8) ?? "" }
    showReview = true; message = "Review the volume profile before applying."
   case "deploy":
    if let d = r as? [String:Any] { profiles = d["profiles"] as? [[String:Any]] ?? []; message = d["message"] as? String ?? "Saved" }
    bridgeOn = true; selectedProfile = "ultrabar-mac-volume"
   case "bridge": message = bridgeOn ? "Volume bridge enabled. Keep this app open." : "Volume bridge paused."
   case "disconnect": connected = false; bridgeOn = false; message = "Disconnected."
   default: message = "Done."
   }
  }
 }
 func send(_ op: String, _ values: [String:Any] = [:]) {
  guard !busy else { return }
  var d = values; d["op"] = op
  guard let data = try? JSONSerialization.data(withJSONObject:d), let pipe = stdinPipe else { return }
  busy = true; error = false
  message = op == "scan" ? "Looking for modules…" : (op == "pair" ? "Tap Allow on the Ultrabar when prompted…" : "Working…")
  do { try pipe.fileHandleForWriting.write(contentsOf:data + Data([10])) }
  catch { busy = false; self.error = true; message = error.localizedDescription }
 }
 func stop() { try? stdinPipe?.fileHandleForWriting.close(); process?.terminate() }
 var hasKnob: Bool { modules.contains { ($0["productId"] as? Int) == 268435458 && ($0["available"] as? Bool ?? true) } }
 func moduleName(_ m:[String:Any]) -> String { [268435457:"DotKey",268435458:"KnobKey",268435459:"VivoCube",268435460:"SenseCube"][m["productId"] as? Int ?? 0] ?? "Module" }
}

struct ContentView: View {
 @StateObject var model = Model()
 @State private var selected = "Device"
 let sections = ["Device", "Widgets", "Mac buttons", "Screen", "Mac volume"]
 var body: some View {
  NavigationSplitView {
   VStack(alignment:.leading,spacing:20) {
    VStack(alignment:.leading,spacing:5) {
     Image(systemName:"slider.horizontal.3").font(.system(size:30,weight:.medium)).foregroundStyle(.mint)
     Text("Ultrabar Mac").font(.title2.bold())
     Text("Your desk, connected.").font(.caption).foregroundStyle(.secondary)
    }.padding(.top,20)
    ForEach(sections,id:\.self) { name in
     Button { selected = name } label: {
      Label(name,systemImage:name == "Device" ? "cable.connector" : name == "Screen" ? "display" : name == "Widgets" ? "square.grid.2x2" : "speaker.wave.2")
       .frame(maxWidth:.infinity,alignment:.leading).padding(10)
       .background(selected == name ? Color.mint.opacity(0.16) : Color.clear,in:RoundedRectangle(cornerRadius:8))
     }.buttonStyle(.plain)
    }
    Spacer()
    Label(model.connected ? "Connected" : "Offline",systemImage:model.connected ? "checkmark.circle.fill" : "circle")
     .font(.caption).foregroundStyle(model.connected ? .mint : .secondary)
    Text("Experimental • v0.4.2").font(.caption2).foregroundStyle(.secondary)
   }.padding(18).frame(minWidth:185)
  } detail: {
   VStack(alignment:.leading,spacing:0) {
    ScrollView {
     VStack(alignment:.leading,spacing:24) {
      Text(selected).font(.system(size:30,weight:.bold))
      if selected == "Device" { deviceView }
      if selected == "Screen" { screenView }
      if selected == "Widgets" { WidgetEditorView(model:model) }
      if selected == "Mac buttons" { MacActionsView(model:model).onAppear { if !model.macLoaded && !model.busy { model.send("actions_load") } } }
      if selected == "Mac volume" { volumeView }
     }.padding(30).frame(maxWidth:(selected == "Widgets" || selected == "Mac buttons") ? 1050 : 760,alignment:.leading)
    }
    Divider()
    HStack(spacing:10) {
     if model.busy { ProgressView().controlSize(.small) }
     else { Image(systemName:model.error ? "exclamationmark.circle" : "info.circle").foregroundStyle(model.error ? .orange : .secondary) }
     Text(model.message).font(.callout).textSelection(.enabled)
     Spacer()
    }.padding(16).frame(minHeight:58)
   }
  }
  .frame(minWidth:1080,minHeight:780)
  .onAppear { model.start(); model.send("widget_load"); if let tab=ProcessInfo.processInfo.environment["ULTRABAR_PREVIEW_SECTION"] { selected=tab } }
  .onReceive(NotificationCenter.default.publisher(for:NSApplication.willTerminateNotification)) { _ in model.stop() }
  .sheet(isPresented:$model.showReview) { reviewView }
  .sheet(isPresented:$model.showMacReview) { MacButtonsReview(model:model) }
  .sheet(isPresented:$model.showWidgetReview) { WidgetReviewView(model:model) }
 }
 var deviceView: some View {
  VStack(alignment:.leading,spacing:22) {
   Text("Connect over the same Wi-Fi network. Pairing is approved on the Ultrabar itself.").foregroundStyle(.secondary)
   GroupBox {
    VStack(alignment:.leading,spacing:14) {
     Text("CoreBAR").font(.headline)
     HStack {
      TextField("IP address",text:$model.host).textFieldStyle(.roundedBorder).frame(width:190).disabled(model.connected)
      Button("Connect") { model.send("connect",["host":model.host]) }.disabled(model.connected || model.busy)
      Button("Pair") { model.send("pair",["host":model.host]) }.disabled(model.connected || model.busy)
      if model.connected { Button("Disconnect") { model.send("disconnect") }.disabled(model.busy) }
     }
     Text("TLS connection with the verified vendor certificate.").font(.caption).foregroundStyle(.secondary)
    }.padding(12).frame(maxWidth:.infinity,alignment:.leading)
   }
   HStack { Text("Modules").font(.title3.bold()); Spacer(); Button("Scan modules") { model.send("scan") }.disabled(!model.connected || model.busy) }
   if model.modules.isEmpty {
    VStack(spacing:10) { Image(systemName:"square.stack.3d.up").font(.largeTitle).foregroundStyle(.secondary); Text("Scan to find your magnetic modules.").foregroundStyle(.secondary) }.frame(maxWidth:.infinity).padding(28)
   } else {
    ForEach(model.modules.indices,id:\.self) { i in
     let m=model.modules[i]
     HStack(spacing:16) {
      Image(systemName:model.moduleName(m) == "KnobKey" ? "dial.medium" : "square.on.circle").font(.title).foregroundStyle(.mint).frame(width:42)
      VStack(alignment:.leading,spacing:4) { Text(model.moduleName(m)).font(.headline); Text(m["serialNumber"] as? String ?? "").font(.system(.caption,design:.monospaced)).foregroundStyle(.secondary).textSelection(.enabled) }
      Spacer(); Text(m["status"] as? String ?? "Seen in scan").font(.caption).foregroundStyle((m["registeredOnline"] as? Bool) == false ? Color.orange : Color.mint)
     }.padding(16).background(Color.primary.opacity(0.04),in:RoundedRectangle(cornerRadius:12))
    }
   }
   Divider()
   Text("Saved profiles").font(.headline)
   HStack {
    Picker("Profile",selection:$model.selectedProfile) { ForEach(model.profiles.indices,id:\.self) { i in Text(model.profiles[i]["label"] as? String ?? "Profile").tag(model.profiles[i]["value"] as? String ?? "") } }.labelsHidden().frame(maxWidth:260)
    Button("Switch") { model.send("switch",["profile":model.selectedProfile]) }.disabled(!model.connected || model.busy || model.selectedProfile.isEmpty)
    Button("Refresh") { model.send("refresh") }.disabled(!model.connected || model.busy)
   }
  }
 }
 var screenView: some View {
  VStack(alignment:.leading,spacing:24) {
   WallpaperView(model:model)
   Text("Set when the Ultrabar enters its screensaver. Changes are read back from the device after saving.").foregroundStyle(.secondary)
   GroupBox {
    VStack(alignment:.leading,spacing:22) {
     Toggle("Enable screensaver",isOn:$model.screenEnabled)
     Picker("After inactivity",selection:$model.screenTime) {
      Text("30 seconds").tag("TIME_30S")
      Text("1 minute").tag("TIME_1MIN")
      Text("2 minutes").tag("TIME_2MIN")
      Text("3 minutes").tag("TIME_3MIN")
      Text("4 minutes").tag("TIME_4MIN")
      Text("5 minutes").tag("TIME_5MIN")
      Text("Never").tag("NEVER")
     }.frame(maxWidth:340)
     if !model.screenSaved { Text("No saved screensaver settings were returned. These are proposed defaults.").font(.caption).foregroundStyle(.secondary) }
    }.padding(16).frame(maxWidth:.infinity,alignment:.leading)
   }.disabled(!model.connected || model.busy)
   Button("Save screen settings") { model.send("screen",["enabled":model.screenEnabled,"lockTime":model.screenTime]) }.buttonStyle(.borderedProminent).tint(.mint).disabled(!model.connected || model.busy)
  }
 }
 var volumeView: some View {
  VStack(alignment:.leading,spacing:22) {
   Text("Use KnobKey to control the Mac’s system volume while this app is open.").foregroundStyle(.secondary)
   GroupBox {
    VStack(alignment:.leading,spacing:16) {
     HStack { Image(systemName:"speaker.wave.2.fill").font(.largeTitle).foregroundStyle(.mint); VStack(alignment:.leading) { Text("Mac volume bridge").font(.headline); Text(model.volumeText).font(.caption).foregroundStyle(.secondary) }; Spacer() }
     Toggle("Respond to volume requests",isOn:$model.bridgeOn).onChange(of:model.bridgeOn) { _, value in
      if !model.busy { model.send("bridge",["enabled":value]) }
     }
     Text("Requires a PC-volume binding on the Ultrabar. Audio outputs with fixed volume may not respond.").font(.caption).foregroundStyle(.secondary)
    }.padding(16)
   }.disabled(!model.connected || model.busy)
   Text("Create a volume profile").font(.title3.bold())
   Text("This experimental setup binds both rotation directions to Mac volume. Knob press actions and VivoCube layouts are not included in this version.").foregroundStyle(.secondary)
   TextField("Profile name",text:$model.profileName).textFieldStyle(.roundedBorder).frame(maxWidth:320)
   Label("Replaces the current profiles and screen widgets",systemImage:"exclamationmark.triangle").foregroundStyle(.orange)
   Text("The new profile has no screen widgets. The current layout cannot be restored from this app. Review the complete change before applying.").font(.callout).foregroundStyle(.secondary)
   HStack {
    if !model.hasKnob { Button("Find KnobKey") { model.send("scan") }.disabled(!model.connected || model.busy) }
    Button("Review volume profile…") { model.send("draft",["name":model.profileName]) }.disabled(!model.connected || model.busy || !model.hasKnob)
   }
  }
 }
 var reviewView: some View {
  VStack(alignment:.leading,spacing:16) {
   Text("Review volume profile").font(.title2.bold())
   Text("Applying will replace the saved profiles, clear their screen widgets, register the detected wired modules, and activate Mac Volume. It also replaces gateway registration, including wireless modules. This app cannot back up the original layout.").foregroundStyle(.orange)
   Text("Detected: \(model.modules.map{model.moduleName($0)}.joined(separator:", "))").font(.headline)
   Text("Current profiles: \(model.profiles.compactMap{$0["label"] as? String}.joined(separator:", "))")
   ScrollView { Text(model.draftText).font(.system(.caption,design:.monospaced)).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading) }.frame(height:240).padding(12).background(Color.primary.opacity(0.04),in:RoundedRectangle(cornerRadius:10))
   Text("Deployment and physical knob operation have not yet been tested on your device.").font(.caption).foregroundStyle(.secondary)
   HStack {
    Button("Cancel") { model.showReview=false }.keyboardShortcut(.cancelAction)
    Spacer()
    Button("Replace profiles and apply",role:.destructive) { model.showReview=false; model.send("deploy",["name":model.profileName,"confirmReplace":true,"expectedProfiles":model.profiles]) }
   }
  }.padding(28).frame(width:620)
 }
}
@main struct UltrabarMacApp: App {
 init() { NSApplication.shared.setActivationPolicy(.regular) }
 var body: some Scene { WindowGroup("Ultrabar Mac") { ContentView() }.windowStyle(.titleBar).commands { CommandGroup(replacing:.newItem) {} } }
}
