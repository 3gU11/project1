import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "D:/CURSORpj/V8BetaV1.1/2026.7.2\u5408\u540c_\u672a\u627e\u5230.xlsx";
const tempPath = "D:/CURSORpj/V8BetaV1.1/2026.7.2\u5408\u540c_\u672a\u627e\u5230.customer_fixed.xlsx";
const previewPath = "D:/CURSORpj/V8BetaV1.1/missing_contracts_customer_fixed_preview.png";

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Sheet1");

const fills = [
  [18, "\u82cf\u5dde\u6167\u63a7\u81ea\u52a8\u5316", "\u5434\u4e2d\u8d8a\u6eaa\u8def"],
  [20, "\u7389\u73af\u5e02\u5b8f\u660c\u5f39\u7c27\u5236\u9020", "\u73af\u5e02\u5e72\u6c5f"],
  [45, "\u571f\u8033\u5176", "\u571f\u8033\u5176"],
  [52, "\u8fbe\u5dde\u946b\u5b8f\u521b\u65b0\u7cbe\u5bc6\u5de5\u4e1a", "\u56db\u5ddd\u8fbe\u5dde"],
  [75, "\u6d59\u6c5f\u73af\u901f\u79d1\u6280\u80a1\u4efd", "\u4f59\u59da\u5e02\u6cd7\u95e8\u9547"],
  [95, "\u9752\u5c9b\u4e07\u529b\u901a\u7cbe\u5bc6\u5de5\u4e1a", "\u9752\u5c9b\u5e02\u57ce\u9633\u533a"],
];

for (const [row, customer, location] of fills) {
  sheet.getRange(`D${row}:F${row}`).values = [[customer, null, location]];
}

const preview = await workbook.render({
  sheetName: "Sheet1",
  range: "A70:I95",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(tempPath);
await fs.copyFile(tempPath, workbookPath);
await fs.rm(tempPath);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Sheet1",
  range: "A70:I95",
  include: "values,formulas",
  tableMaxRows: 30,
  tableMaxCols: 9,
  maxChars: 5000,
});
console.log(check.ndjson);
console.log(`saved=${workbookPath}`);
console.log(`preview=${previewPath}`);
