import { renderAsync } from 'docx-preview'

export async function contractPreviewHtml(bytes: ArrayBuffer): Promise<string> {
  const body = document.createElement('div')
  const styles = document.createElement('div')
  await renderAsync(bytes, body, styles, {
    className: 'contract-docx', inWrapper: true,
    ignoreWidth: false, ignoreHeight: false, ignoreFonts: false,
    breakPages: true, renderHeaders: true, renderFooters: true,
    renderFootnotes: true, renderEndnotes: true,
    renderAltChunks: false, renderChanges: false, renderComments: false,
    useBase64URL: true,
  })
  if (!body.querySelector('section')) throw new Error('未能生成合同页面')
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:;"><style>body{margin:0;background:#e9edf2} .contract-docx-wrapper{padding:24px!important;background:#e9edf2!important} section.contract-docx{margin-bottom:24px!important;box-shadow:0 2px 10px #0002}</style>${styles.innerHTML}</head><body>${body.innerHTML}</body></html>`
}
