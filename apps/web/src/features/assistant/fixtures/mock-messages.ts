import type { UIMessage } from 'ai'

const msg = (id: string, role: UIMessage['role'], text: string): UIMessage => ({
  id,
  role,
  parts: [{ type: 'text', text }],
})

export const MOCK_MESSAGES: UIMessage[] = [
  msg('1', 'user', 'Hey, can you draft a quick email to my team about the Q3 planning meeting next Thursday at 2pm?'),
  msg('2', 'assistant', "Sure! Here's a draft:\n\nSubject: Q3 Planning Meeting — Thursday at 2pm\n\nHi team,\n\nJust a heads-up that we have our Q3 planning meeting scheduled for this Thursday at 2:00pm. Please come prepared with your current priorities and any blockers you'd like to discuss.\n\nLet me know if you have any conflicts.\n\nThanks"),
  msg('3', 'user', 'Nice, can you also add a calendar invite for it?'),
  msg('4', 'assistant', 'Done — calendar invite sent to the team for Thursday at 2pm with the meeting details included.'),
  msg('5', 'user', 'What do I have on my calendar tomorrow?'),
  msg('6', 'assistant', "Here's what's on your calendar for tomorrow:\n\n• 9:00am — Standup\n• 11:30am — 1:1 with Sarah\n• 3:00pm — Design review\n\nLooks like your afternoon is mostly free after 4pm."),
  msg('7', 'user', 'Perfect. Can you remind me 30 minutes before the design review?'),
  msg('8', 'assistant', "Done — I'll remind you at 2:30pm tomorrow before the design review."),
]
