import SwiftUI
import AppKit
import ImageIO
import UniformTypeIdentifiers

extension Model {
 func chooseWallpaper() {
  let panel=NSOpenPanel();panel.allowedContentTypes=[.png,.jpeg,.heic,.tiff,.webP];panel.allowsMultipleSelection=false
  panel.message="Choose a picture to preview on the Ultrabar. It will be cropped to fit the wide screen."
  guard panel.runModal() == .OK, let url=panel.url else { return }
  do {
   let size=try url.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? 0
   guard size>0 && size<=30*1024*1024 else { throw NSError(domain:"Wallpaper",code:1,userInfo:[NSLocalizedDescriptionKey:"Choose an image smaller than 30 MB."]) }
   guard let source=CGImageSourceCreateWithURL(url as CFURL,nil),let thumbnail=CGImageSourceCreateThumbnailAtIndex(source,0,[kCGImageSourceCreateThumbnailFromImageAlways:true,kCGImageSourceCreateThumbnailWithTransform:true,kCGImageSourceThumbnailMaxPixelSize:2848] as CFDictionary),let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1424,pixelsHigh:280,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0),let context=NSGraphicsContext(bitmapImageRep:bitmap) else { throw NSError(domain:"Wallpaper",code:2,userInfo:[NSLocalizedDescriptionKey:"This image could not be opened."]) }
   NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=context
   NSColor.black.setFill();NSRect(x:0,y:0,width:1424,height:280).fill()
   let w=CGFloat(thumbnail.width),h=CGFloat(thumbnail.height),scale=max(1424/w,280/h)
   NSImage(cgImage:thumbnail,size:NSSize(width:w,height:h)).draw(in:NSRect(x:(1424-w*scale)/2,y:(280-h*scale)/2,width:w*scale,height:h*scale),from:.zero,operation:.sourceOver,fraction:1)
   NSGraphicsContext.restoreGraphicsState()
   guard let data=bitmap.representation(using:.png,properties:[:]) else { return }
   wallpaperData=data;wallpaperImage=NSImage(data:data);wallpaperName=url.lastPathComponent
   message="Image ready. Review the crop, then show it on the Ultrabar.";error=false
  } catch { self.error=true;message=error.localizedDescription }
 }
}

struct WallpaperView: View {
 @ObservedObject var model:Model
 var body:some View {
  VStack(alignment:.leading,spacing:14) {
   Text("Wallpaper preview").font(.headline)
   Text("Show a picture full-screen on CoreBAR. Tap the device screen to return to your widgets. This is a temporary preview; it does not set the home-screen background or an automatic screensaver.").font(.callout).foregroundStyle(.secondary)
   ZStack {
    RoundedRectangle(cornerRadius:10).fill(Color.black)
    if let picture=model.wallpaperImage { Image(nsImage:picture).resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius:10)) }
    else { Label("Choose a picture",systemImage:"photo").foregroundStyle(.secondary) }
   }.aspectRatio(1424/280,contentMode:.fit)
   Text(model.wallpaperName).font(.caption).foregroundStyle(.secondary)
   HStack {
    Button("Choose image…") { model.chooseWallpaper() }.disabled(model.busy)
    Button("Show on Ultrabar") { if let data=model.wallpaperData { model.send("wallpaper_show",["image":data.base64EncodedString()]) } }.buttonStyle(.borderedProminent).tint(.mint).disabled(!model.connected || model.busy || model.wallpaperData == nil)
   }
  }.padding(18).background(Color.primary.opacity(0.04),in:RoundedRectangle(cornerRadius:12))
 }
}
