import Foundation
import ImageIO
import Vision

for path in CommandLine.arguments.dropFirst() {
    var faceCount = 0
    let url = URL(fileURLWithPath: path)
    if let source = CGImageSourceCreateWithURL(url as CFURL, nil),
       let image = CGImageSourceCreateImageAtIndex(source, 0, nil) {
        let request = VNDetectFaceRectanglesRequest()
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        do {
            try handler.perform([request])
            faceCount = request.results?.count ?? 0
        } catch {
            faceCount = 0
        }
    }
    let payload: [String: Any] = ["path": path, "face_count": faceCount]
    if let data = try? JSONSerialization.data(withJSONObject: payload),
       let output = String(data: data, encoding: .utf8) {
        print(output)
    }
}
