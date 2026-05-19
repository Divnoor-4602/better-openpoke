---
name: props-object
description: Enforces accepting a single typed props object (then destructuring in the body) for React components with more than 6 props, instead of destructuring directly in the parameter list. Use when writing, reviewing, or refactoring components whose parameter list has grown wide.
---

# Props Object Over Wide Parameter Lists

When a React component has **more than 6 props**, do not destructure them in the parameter list. Accept a single `props` argument typed with the component's props type, then destructure in the function body.

The cutoff is strict: **7+ props ⇒ single props object**. 6 or fewer ⇒ inline destructuring is fine.

## The rule

```tsx
// BAD — 11 props destructured in the signature, painful to scan, diff-noisy
export const CalendarEventFooter = ({
  attendees,
  description,
  endDatetime,
  location,
  meetLink,
  onDiscardAll,
  recurrence,
  startDatetime,
  summary,
  terminal = false,
  timezone,
}: CalendarEventFooterProps) => { ... }

// GOOD — clean signature, destructure inside
export const CalendarEventFooter = (props: CalendarEventFooterProps) => {
  const {
    attendees,
    description,
    endDatetime,
    location,
    meetLink,
    onDiscardAll,
    recurrence,
    startDatetime,
    summary,
    terminal = false,
    timezone,
  } = props
  ...
}
```

The **call site does not change** — JSX still passes individual props (`<CalendarEventFooter summary={...} attendees={...} />`). This rule is only about the component's own signature.

## Why

- **Signature scannability.** The function declaration fits on one line; readers see the component name and its props type without scrolling past a column of identifiers.
- **Cleaner diffs.** Adding/removing a prop touches the destructure block in the body, not the function signature. Git blame stays useful.
- **Easier forwarding.** `props` is in scope as a whole, so spreading (`<Inner {...props} />`) or passing the bag to a hook (`useFoo(props)`) is trivial.
- **Default values stay co-located.** `terminal = false` still works inside the body destructure — no behavior change.

## Counting props

Count **distinct props on the type**, including optional and defaulted ones. Do not count `children` separately if it's already in the props type. Rest/spread (`...rest`) counts as the props it represents (use your judgment — if the rest bag is meaningful, you're past the threshold).

## When inline destructuring is still fine

- 6 or fewer props.
- The component is a tiny one-liner where the props list is the function body (e.g., `({ a, b }) => <Foo a={a} b={b} />`).

## Decision checklist

1. Does the props type have **more than 6** members? → use `(props: T)` + body destructure.
2. 6 or fewer? → inline destructure is fine; do whatever the surrounding file prefers.
3. Refactoring an existing wide signature? → flip it to the props-object form in the same change; do not leave both styles in one file.

## Smell test

You are scrolling past a vertical wall of identifiers to find the opening brace of the function body. Stop and rewrite the signature as `(props: T) => { const { ... } = props; ... }`.
