// ocr.swift — macOS Vision OCR（固定脚本，避免每次内联编译）
//
// 用法:  swift ocr.swift <image> [--json]
//   - 默认按自然阅读顺序输出每行文本（每行一行）
//   - --json 输出 [{text, midY, minX, confidence}]
//
// 性能: ~1s/张（VNRecognizeTextRequest .accurate）
// 排序: 按 boundingBox midY 降序（上→下），同行按 minX 升序（左→右）
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("用法: swift ocr.swift <image> [--json]\n".data(using: .utf8)!)
    exit(1)
}
let path = args[1]
let asJSON = args.contains("--json")

guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("无法读取图片: \(path)\n".data(using: .utf8)!)
    exit(2)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "en-US"]

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([request])

struct Line {
    let text: String
    let midY: CGFloat
    let minX: CGFloat
    let height: CGFloat
    let confidence: Float
}

var lines: [Line] = []
for cand in request.results ?? [] {
    guard let top = cand.topCandidates(1).first else { continue }
    let bb = cand.boundingBox  // 归一化坐标，原点在左下
    let s = top.string.trimmingCharacters(in: .whitespacesAndNewlines)
    if s.isEmpty { continue }
    lines.append(Line(text: s, midY: bb.midY, minX: bb.minX, height: bb.height, confidence: top.confidence))
}

if lines.isEmpty {
    exit(0)  // 无识别文本，输出空
}

// 自然阅读顺序：先按 midY 降序（上→下），同一行内按 minX 升序（左→右）
lines.sort { $0.midY > $1.midY }

// 行高容差 = 中位行高 * 0.6，用于把同一视觉行的文字归并
let hs = lines.map { $0.height }.sorted()
let medianH = hs.count % 2 == 0 ? (hs[hs.count / 2] + hs[hs.count / 2 - 1]) / 2 : hs[hs.count / 2]
let tol = max(medianH * 0.6, 0.004)

var rows: [[Line]] = []
for ln in lines {
    if let idx = rows.firstIndex(where: { abs($0.first!.midY - ln.midY) < tol }) {
        rows[idx].append(ln)
    } else {
        rows.append([ln])
    }
}
let ordered = rows.map { $0.sorted { $0.minX < $1.minX } }

if asJSON {
    let arr: [[String: Any]] = ordered.flatMap { $0 }.map {
        ["text": $0.text, "midY": Double($0.midY), "minX": Double($0.minX),
         "height": Double($0.height), "confidence": Double($0.confidence)]
    }
    if let data = try? JSONSerialization.data(withJSONObject: arr, options: [.prettyPrinted, .sortedKeys]),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    }
} else {
    for row in ordered {
        for ln in row {
            print(ln.text)
        }
    }
}
