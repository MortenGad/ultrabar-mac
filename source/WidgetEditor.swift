import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct WidgetItem: Codable, Identifiable, Equatable {
 var id: String
 var kind: String
 var name: String
 var duration: String
 var offset: String
 var soundId: String? = nil
 var latitude: String? = nil
 var longitude: String? = nil
 var appId: String
 static func make(_ kind:String) -> WidgetItem {
  WidgetItem(id:UUID().uuidString,kind:kind,name:["TIME":"Local time","TIMER":"Focus","WORLD_TIME":"UTC","SOUNDSCAPE":"Soundscape","WEATHER":"Haderslev","APPS":"Calculator"][kind] ?? "Widget",duration:"00:25:00",offset:"+00:00",appId:kind == "APPS" ? "com.ultrabar.calculator" : "")
 }
 var symbol:String { ["TIME":"clock","TIMER":"timer","WORLD_TIME":"globe","SOUNDSCAPE":"waveform","WEATHER":"cloud.sun","APPS":"app.dashed"][kind] ?? "square" }
 var typeName:String { ["TIME":"Clock","TIMER":"Timer","WORLD_TIME":"World clock","SOUNDSCAPE":"Soundscape","WEATHER":"Weather","APPS":"App launcher"][kind] ?? kind }
}
struct WidgetDocument: Codable, Equatable {
 var format:String
 var profileId:String
 var name:String
 var showNames:Bool
 var widgets:[WidgetItem]
 static func empty() -> WidgetDocument { WidgetDocument(format:"ultrabar-mac-layout/v1",profileId:"ultrabar-mac-widgets-"+UUID().uuidString.lowercased(),name:"My desk",showNames:true,widgets:[]) }
 var dictionary:[String:Any] { (try? JSONSerialization.jsonObject(with:JSONEncoder().encode(self))) as? [String:Any] ?? [:] }
}
extension Model {
 func loadWidgetDocument(_ object:Any) {
  do {
   let data=try JSONSerialization.data(withJSONObject:object)
   widgetDocument=try JSONDecoder().decode(WidgetDocument.self,from:data)
   widgetSelection=widgetDocument.widgets.first?.id
  } catch { self.error=true; message="Unable to open layout: \(error.localizedDescription)" }
 }
 func discardWidgetChanges() -> Bool {
  guard widgetDirty else { return true }
  let a=NSAlert();a.messageText="Discard unsaved widget edits?";a.informativeText="Save or export your draft first if you want to keep it. The Ultrabar has not been changed."
  a.addButton(withTitle:"Cancel");a.addButton(withTitle:"Discard edits")
  return a.runModal() == .alertSecondButtonReturn
 }
 func newWidgetDocument() {
  guard discardWidgetChanges() else { return }
  widgetDocument = .empty();widgetSelection=nil;message="New empty layout. Add a widget to begin."
 }
 func openWidgetDocument() {
  guard discardWidgetChanges() else { return }
  let panel=NSOpenPanel();panel.allowedContentTypes=[.json];panel.allowsMultipleSelection=false;panel.canChooseDirectories=false
  guard panel.runModal() == .OK, let url=panel.url else { return }
  do {
   let values=try url.resourceValues(forKeys:[.fileSizeKey]);guard (values.fileSize ?? 0)<=262144 else { throw NSError(domain:"Layout exceeds 256 KB",code:1) }
   let data=try Data(contentsOf:url);let doc=try JSONDecoder().decode(WidgetDocument.self,from:data)
   send("widget_validate",["document":doc.dictionary])
  } catch { self.error=true;message="Could not open this layout: \(error.localizedDescription)" }
 }
 func exportWidgetDocument(_ object:Any) {
  let panel=NSSavePanel();panel.allowedContentTypes=[.json];panel.nameFieldStringValue="Ultrabar Layout.json"
  guard panel.runModal() == .OK,let url=panel.url else { message="Export cancelled.";return }
  do { try JSONSerialization.data(withJSONObject:object,options:[.prettyPrinted,.sortedKeys]).write(to:url,options:.atomic);message="Layout exported. No device settings changed." }
  catch { self.error=true;message="Export failed: \(error.localizedDescription)" }
 }
 func addWidget(_ kind:String) {
  guard widgetDocument.widgets.count<24 else { return }
  var w=WidgetItem.make(kind)
  if kind == "APPS",let app=widgetApps.first(where:{$0["last"] as? Bool == true && $0["type"] as? String == "APPS"}) { w.appId=app["id"] as? String ?? w.appId;w.name=app["name"] as? String ?? w.name }
  if kind == "SOUNDSCAPE",let sound=widgetSounds.first { w.soundId=sound["id"] as? String;w.name=sound["name"] as? String ?? "Soundscape" }
  if kind == "WEATHER" { w.latitude="55.24943";w.longitude="9.48771" }
  widgetDocument.widgets.append(w);widgetSelection=w.id
 }
 func moveWidget(_ id:String,by distance:Int) {
  guard let i=widgetDocument.widgets.firstIndex(where:{$0.id==id}) else { return }
  let j=i+distance;guard widgetDocument.widgets.indices.contains(j) else { return }
  widgetDocument.widgets.swapAt(i,j)
 }
 func dropWidget(_ id:String,before target:String) -> Bool {
  guard id != target,let a=widgetDocument.widgets.firstIndex(where:{$0.id==id}),let b=widgetDocument.widgets.firstIndex(where:{$0.id==target}) else { return false }
  let item=widgetDocument.widgets.remove(at:a);widgetDocument.widgets.insert(item,at:b);widgetSelection=id;return true
 }
 func removeWidget(_ id:String) {
  guard let i=widgetDocument.widgets.firstIndex(where:{$0.id==id}) else { return }
  widgetDocument.widgets.remove(at:i);widgetSelection=widgetDocument.widgets.isEmpty ? nil : widgetDocument.widgets[min(i,widgetDocument.widgets.count-1)].id
 }
}

struct WidgetEditorView: View {
 @ObservedObject var model:Model
 let kinds=["TIME","WORLD_TIME","TIMER","WEATHER","SOUNDSCAPE","APPS"]
 var body:some View {
  VStack(alignment:.leading,spacing:20) {
   HStack(spacing:10) {
    TextField("Layout name",text:$model.widgetDocument.name).font(.title3.weight(.semibold)).textFieldStyle(.roundedBorder).frame(maxWidth:300)
    Text(model.widgetDirty ? "Unsaved draft" : "Saved on this Mac").font(.caption).foregroundStyle(.secondary)
    Spacer()
    Menu("Add widget") { ForEach(kinds,id:\.self) { kind in Button(WidgetItem.make(kind).typeName) { model.addWidget(kind) } } }.disabled(model.widgetDocument.widgets.count>=24)
   }
   HStack(spacing:10) {
    Button("New") { model.newWidgetDocument() }
    Button("Open…") { model.openWidgetDocument() }
    Button("Save draft") { model.send("widget_save",["document":model.widgetDocument.dictionary]) }
    Button("Export…") { model.exportRequested=true;model.send("widget_validate",["document":model.widgetDocument.dictionary]) }
    Spacer()
    Toggle("Show labels",isOn:$model.widgetDocument.showNames).toggleStyle(.checkbox)
   }.disabled(model.busy)
   VStack(alignment:.leading,spacing:12) {
    HStack { Text("Layout preview").font(.headline);Spacer();Text("\(model.widgetDocument.widgets.count) / 24 widgets").font(.caption).foregroundStyle(.secondary) }
    ScrollView(.horizontal) {
     HStack(spacing:12) {
      if model.widgetDocument.widgets.isEmpty {
       VStack(spacing:8) { Image(systemName:"plus.rectangle.on.rectangle").font(.largeTitle);Text("Add your first widget").font(.headline);Text("Clock, timer, world clock, or app launcher").font(.caption) }.foregroundStyle(.secondary).frame(width:640,height:145)
      }
      ForEach(model.widgetDocument.widgets) { w in
       Button { model.widgetSelection=w.id } label: { WidgetTile(widget:w,showName:model.widgetDocument.showNames,selected:model.widgetSelection==w.id) }
        .buttonStyle(.plain).draggable(w.id)
        .dropDestination(for:String.self) { ids,_ in guard let id=ids.first else { return false };return model.dropWidget(id,before:w.id) }
      }
     }.padding(8)
    }
    Text("Drag cards to reorder. This preview shows content and order; the Ultrabar controls the final appearance.").font(.caption).foregroundStyle(.secondary)
   }.padding(16).background(Color.black.opacity(0.18),in:RoundedRectangle(cornerRadius:14))
   HStack(alignment:.top,spacing:20) {
    VStack(alignment:.leading,spacing:8) {
     Text("Widgets").font(.headline)
     ForEach(Array(model.widgetDocument.widgets.enumerated()),id:\.element.id) { index,w in
      Button { model.widgetSelection=w.id } label: {
       HStack(spacing:9) { Text("\(index+1)").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width:16);Image(systemName:w.symbol).foregroundStyle(.mint);Text(w.name).lineLimit(1);Spacer() }
        .padding(10).background(model.widgetSelection==w.id ? Color.mint.opacity(0.13) : Color.primary.opacity(0.03),in:RoundedRectangle(cornerRadius:7))
      }.buttonStyle(.plain)
     }
    }.frame(width:235)
    Divider()
    if let i=model.widgetDocument.widgets.firstIndex(where:{$0.id==model.widgetSelection}) {
     WidgetInspector(widget:$model.widgetDocument.widgets[i],apps:model.widgetApps,sounds:model.widgetSounds,refreshSounds:{model.send("widget_sounds")},connected:model.connected)
    } else { Text("Select a widget to edit its settings.").foregroundStyle(.secondary).frame(maxWidth:.infinity,alignment:.leading).padding(.top,30) }
   }.frame(minHeight:180)
   if let id=model.widgetSelection,let i=model.widgetDocument.widgets.firstIndex(where:{$0.id==id}) {
    HStack {
     Button { model.moveWidget(id,by:-1) } label:{ Label("Move left",systemImage:"arrow.left") }.disabled(i==0)
     Button { model.moveWidget(id,by:1) } label:{ Label("Move right",systemImage:"arrow.right") }.disabled(i==model.widgetDocument.widgets.count-1)
     Spacer();Button("Remove widget",role:.destructive) { model.removeWidget(id) }
    }
   }
   Divider()
   HStack(alignment:.center,spacing:20) {
    VStack(alignment:.leading,spacing:5) {
     Text("Local draft — not imported from the device").font(.callout.weight(.medium))
     Text("Current device layouts cannot be downloaded. Review will list any profiles this deployment would replace.").font(.caption).foregroundStyle(.secondary)
    }
    Spacer()
    Button("Review & apply…") { model.send("widget_review",["document":model.widgetDocument.dictionary]) }.buttonStyle(.borderedProminent).tint(.mint).disabled(!model.connected || model.busy || model.widgetDocument.widgets.isEmpty)
   }
  }.disabled(model.busy)
 }
}

struct WidgetTile:View {
 let widget:WidgetItem
 let showName:Bool
 let selected:Bool
 func clock(_ date:Date) -> String {
  let f=DateFormatter();f.dateFormat="HH:mm"
  if widget.kind=="WORLD_TIME" {
   let parts=widget.offset.dropFirst().split(separator:":");let hours=Int(parts.first ?? "0") ?? 0;let minutes=parts.count>1 ? Int(parts[1]) ?? 0 : 0
   let seconds=(min(max(hours,0),14)*3600+min(max(minutes,0),59)*60)*(widget.offset.hasPrefix("-") ? -1 : 1);f.timeZone=TimeZone(secondsFromGMT:seconds)
  }
  return f.string(from:date)
 }
 var body:some View {
  VStack(alignment:.leading,spacing:12) {
   HStack { Image(systemName:widget.symbol).font(.title3).foregroundStyle(.mint);Spacer();Text(widget.typeName).font(.caption2).foregroundStyle(.secondary) }
   Spacer(minLength:0)
   if widget.kind=="TIME" || widget.kind=="WORLD_TIME" {
    TimelineView(.periodic(from:.now,by:30)) { context in Text(clock(context.date)).font(.system(size:31,weight:.medium,design:.rounded)).monospacedDigit() }
    if widget.kind=="WORLD_TIME" { Text("UTC\(widget.offset)").font(.caption).foregroundStyle(.secondary) }
   } else if widget.kind=="TIMER" { Text(widget.duration).font(.system(size:25,weight:.medium,design:.rounded)).monospacedDigit();Text("Tap to start on device").font(.caption2).foregroundStyle(.secondary) }
   else if widget.kind=="SOUNDSCAPE" { Image(systemName:"waveform").font(.system(size:32)).foregroundStyle(.mint);Text("Tap to play on device").font(.caption2).foregroundStyle(.secondary) }
   else if widget.kind=="WEATHER" { Image(systemName:"cloud.sun").font(.system(size:32)).foregroundStyle(.mint);Text("Forecast on Ultrabar").font(.caption2).foregroundStyle(.secondary) }
   else { Image(systemName:widget.appId.contains("calculator") ? "plus.forwardslash.minus" : widget.appId.contains("alarm") ? "alarm" : "app").font(.system(size:34)).foregroundStyle(.mint) }
   Spacer(minLength:0)
   if showName { Text(widget.name).font(.callout.weight(.medium)).lineLimit(1) }
  }.padding(16).frame(width:160,height:150,alignment:.leading)
   .background(Color.primary.opacity(0.05),in:RoundedRectangle(cornerRadius:13))
   .overlay(RoundedRectangle(cornerRadius:13).stroke(selected ? Color.mint : Color.primary.opacity(0.12),lineWidth:selected ? 2 : 1))
 }
}
struct WidgetInspector:View {
 @Binding var widget:WidgetItem
 let apps:[[String:Any]]
 let sounds:[[String:Any]]
 let refreshSounds:()->Void
 let connected:Bool
 var body:some View {
  VStack(alignment:.leading,spacing:15) {
   Label(widget.typeName,systemImage:widget.symbol).font(.headline)
   VStack(alignment:.leading,spacing:5) { Text("Label").font(.caption).foregroundStyle(.secondary);TextField("Widget label",text:$widget.name).textFieldStyle(.roundedBorder) }
   if widget.kind=="TIMER" {
    VStack(alignment:.leading,spacing:5) { Text("Duration · HH:MM:SS").font(.caption).foregroundStyle(.secondary);TextField("00:25:00",text:$widget.duration).textFieldStyle(.roundedBorder).frame(width:160) }
    HStack { ForEach([5,15,25,45],id:\.self) { n in Button("\(n) min") { widget.duration=String(format:"00:%02d:00",n) } } }
   }
   if widget.kind=="WORLD_TIME" {
    VStack(alignment:.leading,spacing:5) { Text("UTC offset").font(.caption).foregroundStyle(.secondary);TextField("+00:00",text:$widget.offset).textFieldStyle(.roundedBorder).frame(width:160) }
    Text("Use +HH:MM or −HH:MM with a normal minus sign. This is a fixed offset; daylight-saving changes are not automatic.").font(.caption).foregroundStyle(.secondary)
   }
   if widget.kind=="SOUNDSCAPE" {
    if !sounds.isEmpty {
     Picker("Sound",selection:Binding(get:{widget.soundId ?? ""},set:{widget.soundId=$0})) {
      Text("Choose a sound").tag("")
      ForEach(sounds.indices,id:\.self) { i in Text(sounds[i]["name"] as? String ?? "Sound").tag(sounds[i]["id"] as? String ?? "") }
     }
    }
    Button(sounds.isEmpty ? "Load sounds from Ultrabar" : "Refresh sounds",action:refreshSounds).disabled(!connected)
    Text("Select an installed sound. Tap the widget on the Ultrabar to play it.").font(.caption).foregroundStyle(.secondary)
   }
   if widget.kind=="WEATHER" {
    HStack {
     VStack(alignment:.leading) { Text("Latitude").font(.caption);TextField("55.24943",text:Binding(get:{widget.latitude ?? ""},set:{widget.latitude=$0})).textFieldStyle(.roundedBorder) }
     VStack(alignment:.leading) { Text("Longitude").font(.caption);TextField("9.48771",text:Binding(get:{widget.longitude ?? ""},set:{widget.longitude=$0})).textFieldStyle(.roundedBorder) }
    }
    Button("Use Haderslev, Denmark") { widget.latitude="55.24943";widget.longitude="9.48771";widget.name="Haderslev" }
    Text("LineOS fetches the forecast for these coordinates. The Ultrabar needs internet access; this preview does not show live weather.").font(.caption).foregroundStyle(.secondary)
   }
   if widget.kind=="APPS" {
    let leaf=apps.filter{$0["last"] as? Bool == true && $0["type"] as? String == "APPS"}
    if !leaf.isEmpty {
     Picker("App",selection:$widget.appId) {
      if !leaf.contains(where:{$0["id"] as? String == widget.appId}) { Text("Choose an installed app").tag(widget.appId) }
      ForEach(leaf.indices,id:\.self) { i in Text(leaf[i]["name"] as? String ?? "App").tag(leaf[i]["id"] as? String ?? "") }
     }
    } else { Text(connected ? "No supported app launchers were returned." : "Connect to load installed app launchers.").font(.caption).foregroundStyle(.secondary) }
   }
   if widget.kind=="TIME" { Text("Uses the Ultrabar’s own date, time, and clock appearance. The preview uses your Mac’s clock.").font(.caption).foregroundStyle(.secondary) }
  }.frame(maxWidth:.infinity,alignment:.leading)
 }
}
struct WidgetReviewView:View {
 @ObservedObject var model:Model
 @State private var confirmedReplacement=false
 var removed:[String] { model.widgetReview["replacedProfiles"] as? [String] ?? [] }
 var body:some View {
  VStack(alignment:.leading,spacing:20) {
   Text("Apply widget layout").font(.title2.bold())
   Text("\(model.widgetReview["profileName"] as? String ?? "Layout") · \(model.widgetReview["widgetCount"] as? Int ?? 0) widgets").font(.headline)
   if !removed.isEmpty {
    Label("These current profiles will be replaced",systemImage:"exclamationmark.triangle.fill").foregroundStyle(.orange)
    Text(removed.joined(separator:", ")).font(.headline)
    Text("The device does not expose their full layouts. They cannot be restored from this app’s change record.").foregroundStyle(.secondary)
    Toggle("I understand that those profiles and their widgets will be replaced",isOn:$confirmedReplacement).toggleStyle(.checkbox)
   } else { Text("Updates the selected app-managed layout and retains the other locally recorded profiles.").foregroundStyle(.secondary) }
   VStack(alignment:.leading,spacing:8) {
    Text("Profiles after applying").font(.headline)
    Text((model.widgetReview["profilesAfter"] as? [String] ?? []).joined(separator:", "))
    Text("Gateway registration is unchanged. Module bindings are retained where they are present in this app’s local profile record.").font(.caption).foregroundStyle(.secondary)
    Text("External edits to app-managed profiles cannot be detected. The app can verify the profile list after saving, but you must check the actual widgets on the Ultrabar.").font(.caption).foregroundStyle(.secondary)
   }.padding(14).background(Color.primary.opacity(0.04),in:RoundedRectangle(cornerRadius:10))
   HStack {
    Button("Cancel") { model.showWidgetReview=false }.keyboardShortcut(.cancelAction)
    Spacer()
    Button("Apply layout") { model.showWidgetReview=false;model.send("widget_deploy",["reviewId":model.widgetReview["reviewId"] as? String ?? "","confirmed":true,"confirmReplace":confirmedReplacement]) }.buttonStyle(.borderedProminent).tint(.mint).disabled(!removed.isEmpty && !confirmedReplacement)
   }
  }.padding(28).frame(width:590)
 }
}
