import { ConvexError } from 'convex/values'

type NotFoundArgs = {
  entity?: string
  id?: string
  message?: string
}

type NotFoundData = {
  code: 'NOT_FOUND'
  entity?: string
  id?: string
  message: string
}

type ValidationErrorArgs = {
  entity?: string
  id?: string
  message?: string
}

type ValidationErrorData = {
  code: 'VALIDATION_ERROR'
  entity?: string
  id?: string
  message: string
}

export function notFound(args?: NotFoundArgs): never {
  const entity = args?.entity
  const id = args?.id
  const fallback = entity
    ? id
      ? `${entity} not found with id: ${id}`
      : `${entity} not found`
    : 'Not found'
  throw new ConvexError<NotFoundData>({
    code: 'NOT_FOUND',
    entity,
    id,
    message: args?.message ?? fallback,
  })
}

export function validationError(args?: ValidationErrorArgs): never {
  throw new ConvexError<ValidationErrorData>({
    code: 'VALIDATION_ERROR',
    entity: args?.entity,
    id: args?.id,
    message: args?.message ?? 'Validation error',
  })
}
