import { useParams } from '@tanstack/react-router'
import { motion } from 'motion/react'

import { useThread, useUpdateThreadMutation } from '@/lib/poke/thread'

import { ThreadTitle } from '../components/thread-title'

const DEFAULT_THREAD_TITLE = 'New thread'

export function ThreadTitleWidget() {
  const params = useParams({ strict: false })
  const threadId = params.threadId ?? null
  const { data: thread } = useThread(threadId)
  const updateThread = useUpdateThreadMutation(threadId)

  if (!threadId) return null

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      initial={{ opacity: 0, y: -5 }}
      key={threadId}
      transition={{ duration: 0.15, ease: 'easeOut' }}
    >
      <ThreadTitle
        isPending={updateThread.isPending}
        onRename={(title) => updateThread.mutate({ title })}
        title={thread?.title ?? DEFAULT_THREAD_TITLE}
      />
    </motion.div>
  )
}
