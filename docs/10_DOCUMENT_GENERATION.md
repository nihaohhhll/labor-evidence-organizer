# 文档生成

## 输出

1. evidence-index.docx
2. evidence-index.pdf
3. timeline.docx
4. timeline.pdf
5. evidence-bundle.pdf
6. evidence-bundle.zip

## 编号

默认：
证据1、证据2……

多页证据：
证据1-1、证据1-2……

## 页码

统一：
第 X 页 / 共 Y 页

## 规则

- 不改变原始图片内容；
- 编号和页码作为外层排版元素；
- 保留原始清晰度；
- PDF 合并顺序由 evidence_number 决定；
- 导出只读取 confirmed/current user-reviewed 数据；
- 导出完成后生成 immutable export artifact。

## Word

使用 python-docx。
## PDF

优先使用 ReportLab + PyMuPDF。
