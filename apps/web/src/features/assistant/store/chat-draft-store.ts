import { toast } from 'sonner'
import { create } from 'zustand'

type ChatDraftState = {
  /** Push text into the chat input from anywhere in the tree, with a toast. */
  injectDraft: (text: string) => void
  setText: (text: string) => void
  text: string
}

export const useChatDraftStore = create<ChatDraftState>((set) => ({
  injectDraft: (text) => {
    set({ text })
    toast('Details have been added to your prompt')
  },
  setText: (text) => set({ text }),
  text: '',
}))
