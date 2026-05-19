import { useGoogleIntegration } from '../hooks/use-google-integration'
import { GoogleConnectButton } from './google-connect-button'

type GoogleConnectionPromptProps = {
  message?: string
}

export const GoogleConnectionPrompt = ({
  message,
}: GoogleConnectionPromptProps) => {
  const { connect, connected, isConnecting, status } = useGoogleIntegration()

  return (
    <div className="flex flex-col items-start gap-1.5">
      {message ? (
        <p className="text-xs text-muted-foreground">{message}</p>
      ) : null}
      <GoogleConnectButton
        disabled={isConnecting || connected}
        onClick={connect}
        status={status}
      />
    </div>
  )
}
