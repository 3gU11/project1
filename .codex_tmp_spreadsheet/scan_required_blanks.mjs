import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "D:/CURSORpj/V8BetaV1.1/2026.7.2\u5408\u540c_\u672a\u627e\u5230_\u5df2\u8865\u5168.xlsx";
const previewPath = "D:/CURSORpj/V8BetaV1.1/missing_contracts_all_blanks_checked_preview.png";

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Sheet1");

const values = sheet.getRange("A1:I95").values;
const blankFullRows = [];
const blankMandatory = [];
const blankCustomer = [];
const blankDealer = [];

for (let i = 0; i < values.length; i += 1) {
  const rowNo = i + 1;
  const row = values[i];
  const isBlank = (v) => v === null || v === undefined || String(v).trim() === "";
  if (row.every(isBlank)) blankFullRows.push(rowNo);

  const [date, model, qty, d, e, f, dealer] = row;
  const customerBlank = [d, e, f].every(isBlank);
  if (customerBlank) blankCustomer.push(rowNo);
  if (isBlank(dealer)) blankDealer.push(rowNo);
  if (isBlank(date) || isBlank(model) || isBlank(qty) || customerBlank || isBlank(dealer)) {
    blankMandatory.push({
      row: rowNo,
      dateBlank: isBlank(date),
      modelBlank: isBlank(model),
      qtyBlank: isBlank(qty),
      customerBlank,
      dealerBlank: isBlank(dealer),
    });
  }
}

const preview = await workbook.render({
  sheetName: "Sheet1",
  range: "A1:I95",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

console.log(JSON.stringify({
  workbookPath,
  rowCount: values.length,
  blankFullRows,
  blankCustomer,
  blankDealer,
  blankMandatory,
  previewPath,
}, null, 2));
