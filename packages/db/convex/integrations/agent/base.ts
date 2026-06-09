import { openai } from '@ai-sdk/openai'
import { Agent } from '@convex-dev/agent'

import { components } from '../../_generated/api'

const DEFAULT_AGENT_MODEL = 'gpt-5.5'

export const legalAgent = new Agent(components.agent, {
  instructions: [
    'You are a helpful assistant for Legal Poke users.',
    'Be concise, ask clarifying questions when needed, and do not claim integrations are available until their tools are wired in.',
  ].join('\n'),
  languageModel: openai(
    process.env.LEGAL_POKE_AGENT_MODEL ?? DEFAULT_AGENT_MODEL,
  ),
  name: '',
})
