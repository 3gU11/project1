import { onBeforeUnmount, onMounted } from 'vue'
import { INVENTORY_SYNC_EVENT } from './inventorySync'

export const useInventoryAutoRefresh = (refresh: () => void | Promise<void>) => {
  let running = false
  const run = async () => {
    if (running) return
    running = true
    try {
      await refresh()
    } finally {
      running = false
    }
  }
  const onVisible = () => {
    if (document.visibilityState === 'visible') void run()
  }
  const onSync = () => void run()

  onMounted(() => {
    window.addEventListener('focus', onSync)
    window.addEventListener(INVENTORY_SYNC_EVENT, onSync)
    document.addEventListener('visibilitychange', onVisible)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('focus', onSync)
    window.removeEventListener(INVENTORY_SYNC_EVENT, onSync)
    document.removeEventListener('visibilitychange', onVisible)
  })
}
