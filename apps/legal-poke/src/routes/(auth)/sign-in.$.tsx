import { SignIn } from '@clerk/tanstack-react-start'
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/(auth)/sign-in/$')({
  component: SignInPage,
})

function SignInPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <SignIn
        forceRedirectUrl="/"
        path="/sign-in"
        routing="path"
        signUpUrl="/sign-up"
      />
    </main>
  )
}
