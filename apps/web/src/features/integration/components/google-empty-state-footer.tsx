import { useGoogleIntegration } from '../hooks/use-google-integration'
import { GoogleConnectButton } from './google-connect-button'
import { GoogleProductIcons } from './google-product-icons'

export const GoogleEmptyStateFooter = () => {
  const { connect, connected, isConnecting, status } = useGoogleIntegration()

  return (
    <div className="px-2 flex items-center justify-between">
      <GoogleConnectButton
        disabled={isConnecting || connected}
        onClick={connect}
        status={status}
      />
      <GoogleProductIcons connected={connected} />
    </div>
  )
}
