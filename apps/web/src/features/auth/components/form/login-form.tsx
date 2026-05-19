import { useForm } from '@tanstack/react-form'

import { useAuth } from '@/features/auth/hooks/use-auth'

import { AuthInput } from './auth-input'
import { loginSchema } from './schema'
import { SubmitButton } from './submit-button'

const fieldErrorMessage = (
  errors: ReadonlyArray<unknown>,
): string | undefined => {
  const message = errors
    .map((error) =>
      typeof error === 'string'
        ? error
        : (error as null | { message?: string })?.message,
    )
    .filter(Boolean)
    .join(', ')
  return message || undefined
}

export const LoginForm = () => {
  const { login, loginMutation } = useAuth()

  const form = useForm({
    defaultValues: { handle: '', password: 'demo' },
    onSubmit: async ({ value }) => {
      await login(value.handle, value.password)
    },
    validators: { onBlur: loginSchema, onSubmit: loginSchema },
  })

  return (
    <form
      className="flex flex-col gap-6 w-full"
      onSubmit={(event) => {
        event.preventDefault()
        event.stopPropagation()
        void form.handleSubmit()
      }}
    >
      <form.Field name="handle">
        {(field) => (
          <AuthInput
            autoComplete="username"
            disabled={loginMutation.isPending}
            error={
              field.state.meta.isTouched && !field.state.meta.isValid
                ? fieldErrorMessage(field.state.meta.errors)
                : undefined
            }
            id={field.name}
            label="Username"
            name={field.name}
            onBlur={field.handleBlur}
            onChange={(event) => field.handleChange(event.target.value)}
            placeholder="Type your username"
            value={field.state.value}
          />
        )}
      </form.Field>

      <form.Field name="password">
        {(field) => (
          <AuthInput
            autoComplete="current-password"
            disabled={loginMutation.isPending}
            error={
              field.state.meta.isTouched && !field.state.meta.isValid
                ? fieldErrorMessage(field.state.meta.errors)
                : undefined
            }
            id={field.name}
            label="Password"
            name={field.name}
            onBlur={field.handleBlur}
            onChange={(event) => field.handleChange(event.target.value)}
            placeholder="Type your password"
            type="password"
            value={field.state.value}
          />
        )}
      </form.Field>

      {loginMutation.isError ? (
        <p className="text-destructive text-sm">
          {loginMutation.error instanceof Error
            ? loginMutation.error.message
            : 'Invalid username or password.'}
        </p>
      ) : null}

      <form.Subscribe
        selector={(state) => ({
          canSubmit: state.canSubmit,
          isSubmitting: state.isSubmitting,
        })}
      >
        {({ canSubmit, isSubmitting }) => (
          <SubmitButton
            disabled={!canSubmit}
            loading={isSubmitting || loginMutation.isPending}
          >
            Get Started
          </SubmitButton>
        )}
      </form.Subscribe>
    </form>
  )
}
