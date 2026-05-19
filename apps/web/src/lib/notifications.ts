/**
 * Browser-notification helpers.
 *
 * The permission popup is only delivered by browsers when the call is
 * made inside an active user gesture (e.g., a click handler). The
 * agent's chat response cannot trigger the popup itself; the web
 * client triggers it on the user's send-button click. We fire and
 * forget here — by the time the agent's response arrives, the user
 * has either decided or dismissed.
 */

export function notify(title: string, body: string): boolean {
  if (typeof Notification === 'undefined') return false
  if (Notification.permission !== 'granted') return false
  try {
    new Notification(title, { body, icon: '/favicon.svg' })
    return true
  } catch {
    return false
  }
}

export function requestNotificationPermissionIfDefault(): void {
  if (typeof Notification === 'undefined') return
  if (Notification.permission !== 'default') return
  try {
    void Notification.requestPermission()
  } catch {
    // some browsers throw on insecure contexts; ignore.
  }
}
