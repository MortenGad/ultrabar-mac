import SwiftUI
import AppKit
import UniformTypeIdentifiers
struct MacLauncher: Codable, Identifiable {
 var id:String;var name:String;var path:String
}
struct PhysicalAssignment: Codable {
 var serial:String;var productId:Int;var keyCode:Int;var gesture:String;var actionId:String
}
struct MacButtonConfig: Codable {
 var profileName="Mac buttons"
 var actions:[MacLauncher]=[]
 var bindings:[PhysicalAssignment]=[]
 var dictionary:[String:Any] { (try? JSONSerialization.jsonObject(with:JSONEncoder().encode(self))) as? [String:Any] ?? [:] }
}
extension Model {
 func loadMacButtons(_ value:Any) {
  do { macConfig=try JSONDecoder().decode(MacButtonConfig.self,from:JSONSerialization.data(withJSONObject:value));macDirty=false }
  catch { self.error=true;message="Cannot read Mac button settings: \(error.localizedDescription)" }
 }
 func chooseMacApp() {
  let p=NSOpenPanel();p.allowedContentTypes=[.applicationBundle];p.directoryURL=URL(fileURLWithPath:"/Applications");p.canChooseDirectories=false;p.allowsMultipleSelection=false
  guard p.runModal() == .OK,let url=p.url else { return }
  let name=url.deletingPathExtension().lastPathComponent
  macConfig.actions.append(MacLauncher(id:UUID().uuidString,name:name,path:url.path))
 }
 func assignment(_ serial:String,_ key:Int,_ gesture:String)->String { macConfig.bindings.first{$0.serial==serial && $0.keyCode==key && $0.gesture==gesture}?.actionId ?? "" }
 func bindApp(_ value:String,serial:String,product:Int,key:Int,gesture:String) {
  macConfig.bindings.removeAll{$0.serial==serial && $0.keyCode==key && $0.gesture==gesture}
  if !value.isEmpty { macConfig.bindings.append(PhysicalAssignment(serial:serial,productId:product,keyCode:key,gesture:gesture,actionId:value)) }
 }
}
struct MacActionsView:View {
 @ObservedObject var model:Model
 var body:some View {
  VStack(alignment:.leading,spacing:22) {
   Text("Launch Mac apps from your desk").font(.title3.weight(.semibold))
   Text("Choose apps for the touchscreen panel, then reuse them for physical button presses. Keep Ultrabar Mac open and connected.").foregroundStyle(.secondary)
   HStack {
    TextField("Panel name",text:$model.macConfig.profileName).textFieldStyle(.roundedBorder).frame(maxWidth:300)
    Spacer()
    Button("Add Mac app…") { model.chooseMacApp() }.disabled(model.macConfig.actions.count>=12)
   }
   if model.macConfig.actions.isEmpty {
    ContentUnavailableView("Choose your first app",systemImage:"square.grid.3x3",description:Text("Add Mac app creates a named button that opens an application on this Mac."))
   }
   LazyVGrid(columns:[GridItem(.adaptive(minimum:200),spacing:14)],spacing:14) {
    ForEach($model.macConfig.actions) { $a in
     VStack(alignment:.leading,spacing:12) {
      Image(nsImage:NSWorkspace.shared.icon(forFile:a.path)).resizable().frame(width:46,height:46)
      TextField("Button label",text:$a.name).textFieldStyle(.roundedBorder)
      Text(URL(fileURLWithPath:a.path).lastPathComponent).font(.caption).foregroundStyle(.secondary).lineLimit(1)
      HStack {
       Button("Test launch") { model.send("actions_test",["actionId":a.id]) }.disabled(model.macDirty)
       Spacer()
       Button { model.macConfig.bindings.removeAll{$0.actionId==a.id};model.macConfig.actions.removeAll{$0.id==a.id} } label:{ Image(systemName:"trash") }
      }
     }.padding(16).background(Color.primary.opacity(0.045),in:RoundedRectangle(cornerRadius:12))
    }
   }
   HStack {
    Button("Save on Mac") { model.send("actions_save",["config":model.macConfig.dictionary]) }.disabled(model.macConfig.actions.isEmpty)
    Text(model.macDirty ? "Unsaved changes · save before testing" : "Saved on this Mac").font(.caption).foregroundStyle(.secondary)
    Spacer()
    Toggle("Enable app buttons",isOn:$model.macEnabled).onChange(of:model.macEnabled) { _,v in if !model.busy { model.send("actions_enabled",["enabled":v]) } }
   }
   Divider()
   HStack { Text("Physical buttons").font(.headline);Spacer();Button("Scan modules") { model.send("scan") }.disabled(!model.connected) }
   let physical=model.modules.filter{ ($0["productId"] as? Int)==268435457 || ($0["productId"] as? Int)==268435458 }
   if physical.isEmpty { Text("Connect and scan for DotKey and KnobKey modules.").foregroundStyle(.secondary) }
   ForEach(physical.indices,id:\.self) { i in
    let m=physical[i];let serial=m["serialNumber"] as? String ?? "";let product=m["productId"] as? Int ?? 0
    VStack(alignment:.leading,spacing:12) {
     Text(model.moduleName(m)).font(.headline)
     Text(serial).font(.caption.monospaced()).foregroundStyle(.secondary)
     ForEach(product==268435457 ? [1,2,3] : [0],id:\.self) { key in
      HStack {
       Text(product==268435457 ? "Button \(key)" : "Knob press").frame(width:90,alignment:.leading)
       ForEach(["singleClick","doubleClick","longPress"],id:\.self) { gesture in
        Picker(["singleClick":"Press","doubleClick":"Double","longPress":"Hold"][gesture] ?? gesture,selection:Binding(get:{model.assignment(serial,key,gesture)},set:{model.bindApp($0,serial:serial,product:product,key:key,gesture:gesture)})) {
         Text("Unassigned").tag("")
         ForEach(model.macConfig.actions) { a in Text(a.name).tag(a.id) }
        }
       }
      }
     }
    }.padding(16).background(Color.primary.opacity(0.035),in:RoundedRectangle(cornerRadius:10))
   }
   Text("Assignments are active in the Mac buttons profile. Knob rotation is preserved. Physical operation still requires a device test.").font(.caption).foregroundStyle(.secondary)
   HStack {
    Text("Deployment creates or updates a separate profile with a button panel and individual app tiles.").font(.caption).foregroundStyle(.secondary)
    Spacer()
    Button("Review & apply…") { model.send("actions_review",["config":model.macConfig.dictionary]) }.buttonStyle(.borderedProminent).tint(.mint).disabled(!model.connected || model.macConfig.actions.isEmpty)
   }
   Text(model.macEvent).font(.callout).foregroundStyle(.secondary)
  }.disabled(model.busy)
 }
}
struct MacButtonsReview:View {
 @ObservedObject var model:Model
 @State private var replace=false
 var removed:[String] { model.macReview["replacedProfiles"] as? [String] ?? [] }
 var changed:[String] { model.macReview["changedProfiles"] as? [String] ?? [] }
 var body:some View {
  VStack(alignment:.leading,spacing:18) {
   Text("Apply Mac app buttons").font(.title2.bold())
   Text("\(model.macConfig.actions.count) apps · \(model.macConfig.bindings.count) physical assignments")
   Text("Profiles after deployment: \((model.macReview["profilesAfter"] as? [String] ?? []).joined(separator:", "))")
   if !removed.isEmpty {
    Text("These profiles cannot be preserved: \(removed.joined(separator:", ")). Their layouts cannot be restored from this app’s change record.").foregroundStyle(.orange)
   }
   if !changed.isEmpty {
    Text("These profiles changed on the device since this app last applied them: \(changed.joined(separator:", ")). Another tool, such as UltraBar Studio, may have edited them; applying discards those edits.").foregroundStyle(.orange)
   }
   if !removed.isEmpty || !changed.isEmpty {
    Toggle("Replace these profiles",isOn:$replace)
   }
   Text("The app will enable the configured launch buttons. It must stay open and connected.").foregroundStyle(.secondary)
   if (model.macReview["registerModules"] as? Int ?? 0)>0 { Text("The device has no registered modules. This also registers \(model.macReview["registerModules"] as? Int ?? 0) discovered wired modules for physical button events.").foregroundStyle(.secondary) }
   HStack { Button("Cancel") { model.showMacReview=false };Spacer();Button("Apply buttons") { model.showMacReview=false;model.send("actions_deploy",["reviewId":model.macReview["reviewId"] ?? "","confirmed":true,"confirmReplace":replace]) }.buttonStyle(.borderedProminent).disabled((!removed.isEmpty || !changed.isEmpty) && !replace) }
  }.padding(28).frame(width:550)
 }
}
