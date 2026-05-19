---
name: no-use-effect
description: Enforces a strict no-direct-useEffect rule in React/React Native code. Use when writing, reviewing, or refactoring components that use useEffect. Triggers on any React component containing useEffect, data fetching in effects, state-sync effects, mount-time setup, or "reset on prop change" patterns.
license: MIT
metadata:
  author: alejandrobailo
  source: https://github.com/alejandrobailo/no-use-effect
  version: "1.0.0"
---

# No Direct useEffect

Never call `useEffect` directly. For the rare case of syncing with an external system on mount, use `useMountEffect()`.

```tsx
export function useMountEffect(effect: () => void | (() => void)) {
  /* eslint-disable react-hooks/exhaustive-deps, no-restricted-syntax */
  useEffect(effect, []);
}
```

The only place `useEffect` may appear directly is inside reusable custom hooks (like `useMountEffect` itself, or a `useData` hook when no fetching library is available). Components must never import or call `useEffect`.

## The 5 Rules

### Rule 1: Derive state, do not sync it

If you can calculate it from existing state/props, compute it inline.

```tsx
// BAD: two render cycles
const [filteredProducts, setFilteredProducts] = useState([]);
useEffect(() => {
  setFilteredProducts(products.filter((p) => p.inStock));
}, [products]);

// GOOD: one render
const filteredProducts = products.filter((p) => p.inStock);
```

For expensive calculations, use `useMemo`:

```tsx
const visibleTodos = useMemo(
  () => getFilteredTodos(todos, filter),
  [todos, filter]
);
```

**Smell test:** You're about to write `useEffect(() => setX(f(y)), [y])` or state that only mirrors other state/props.

### Rule 2: Use data-fetching libraries

Effect-based fetching creates race conditions and reinvents caching.

```tsx
// BAD: race condition
useEffect(() => {
  fetchProduct(productId).then(setProduct);
}, [productId]);

// GOOD: library handles cancellation/caching/staleness
const { data: product } = useQuery(
  ['product', productId],
  () => fetchProduct(productId)
);
```

**Smell test:** Your effect does `fetch()` then `setState()`, or you're reimplementing caching/retries/cancellation.

### Rule 3: Event handlers, not effects

If a user action triggers it, do the work in the handler.

```tsx
// BAD: flag-relay through effect
const [liked, setLiked] = useState(false);
useEffect(() => {
  if (liked) { postLike(); setLiked(false); }
}, [liked]);

// GOOD: direct
<button onClick={() => postLike()}>Like</button>
```

For shared logic between handlers, extract a function — not an effect:

```tsx
function buyProduct() {
  addToCart(product);
  showNotification(`Added ${product.name}`);
}
```

**Smell test:** State used as a flag so an effect can do the real action, or "set flag → effect runs → reset flag" mechanics.

### Rule 4: useMountEffect for one-time external sync

Only for true mount-time external system setup: DOM integration, third-party widgets, browser API subscriptions.

```tsx
// BAD: guard inside effect
useEffect(() => {
  if (!isLoading) playVideo();
}, [isLoading]);

// GOOD: conditional mounting
function VideoPlayerWrapper({ isLoading }) {
  if (isLoading) return <LoadingScreen />;
  return <VideoPlayer />;
}
function VideoPlayer() {
  useMountEffect(() => playVideo());
}
```

**Smell test:** Behavior is naturally "setup on mount, cleanup on unmount" with an external system.

### Rule 5: Reset with key, not dependency choreography

If you need "start fresh when ID changes," use React's remount semantics.

```tsx
// BAD: effect resets on ID change
useEffect(() => { loadVideo(videoId); }, [videoId]);

// GOOD: key forces clean remount
<VideoPlayer key={videoId} videoId={videoId} />
function VideoPlayer({ videoId }) {
  useMountEffect(() => { loadVideo(videoId); });
}
```

Also applies to resetting form state, clearing selections, etc. Use `key` on the component instead of an effect that sets state to initial values.

**Smell test:** Effect's only job is to reset local state when an ID/prop changes.

## Additional Patterns

### Notifying parents about state changes

Do not use an effect to call `onChange` — update both in the event handler, or lift state up:

```tsx
// BAD
useEffect(() => { onChange(isOn); }, [isOn, onChange]);

// GOOD: update both during the event
function updateToggle(nextIsOn) {
  setIsOn(nextIsOn);
  onChange(nextIsOn);
}
```

### Subscribing to external stores

Use `useSyncExternalStore` instead of manual subscription effects:

```tsx
const isOnline = useSyncExternalStore(
  subscribe,
  () => navigator.onLine,
  () => true
);
```

### App initialization

Run once at module level, not in an effect:

```tsx
if (typeof window !== 'undefined') {
  checkAuthToken();
  loadDataFromLocalStorage();
}
```

### Chains of computations

Never chain effects that trigger each other. Derive values inline and batch state updates in the event handler:

```tsx
// BAD: 3 effects chaining state → 3 extra renders
useEffect(() => { if (card?.gold) setGoldCardCount(c => c + 1); }, [card]);
useEffect(() => { if (goldCardCount > 3) { setRound(r => r + 1); setGoldCardCount(0); } }, [goldCardCount]);
useEffect(() => { if (round > 5) setIsGameOver(true); }, [round]);

// GOOD: derive + handle in event
const isGameOver = round > 5;
function handlePlaceCard(nextCard) {
  setCard(nextCard);
  if (nextCard.gold) {
    if (goldCardCount < 3) setGoldCardCount(goldCardCount + 1);
    else { setGoldCardCount(0); setRound(round + 1); }
  }
}
```

## Decision Checklist

Before writing any effect, answer these in order:

1. Can I compute it during render? → Derive inline or `useMemo`
2. Is it triggered by a user action? → Event handler
3. Am I fetching data? → Data-fetching library (React Query, SWR, etc.)
4. Am I subscribing to an external store? → `useSyncExternalStore`
5. Do I need to reset state when a prop changes? → `key` prop
6. Is it true mount-time external system sync? → `useMountEffect`

If none of the above apply and you still think you need `useEffect`, reconsider — the answer is almost always one of the above.

## Failure Modes

- `useMountEffect` failures are binary and loud: it ran once, or not at all.
- Direct `useEffect` failures degrade gradually as flaky behavior, perf issues, or loops before a hard crash.

Choose the bug that's easy to find.
