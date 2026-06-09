import { SignOutButton, useUser } from '@clerk/tanstack-react-start'

export const Welcome = () => {
  const { user } = useUser()

  if (!user) {
    return null
  }

  return (
    <div className="flex flex-col gap-4">
      Welcome, {user.emailAddresses[0].emailAddress}
      <SignOutButton />
    </div>
  )
}
