/**
 * item_id-based transcript reconciliation for OpenAI Realtime transcription.
 * Completed events from different turns may arrive out of order — never assume order.
 */

export type TranscriptItem = {
  itemId: string
  /** Provisional text accumulated from delta events for this item. */
  provisional: string
  /** Final text from the completed event, if received. */
  completed: string | null
  /** Monotonic first-seen order (not completion order). */
  firstSeenOrder: number
}

export type TranscriptStore = {
  /** Text finalized before the current answer (typed notes, prior takes when preserved). */
  finalizedPrevious: string
  items: Map<string, TranscriptItem>
  nextOrder: number
}

export function createTranscriptStore(finalizedPrevious = ''): TranscriptStore {
  return {
    finalizedPrevious,
    items: new Map(),
    nextOrder: 0,
  }
}

export function applyDelta(store: TranscriptStore, itemId: string, delta: string): TranscriptStore {
  if (!itemId || !delta) return store
  const items = new Map(store.items)
  const existing = items.get(itemId)
  if (existing) {
    // Once completed, ignore further deltas for that item.
    if (existing.completed != null) return store
    items.set(itemId, { ...existing, provisional: `${existing.provisional}${delta}` })
  } else {
    items.set(itemId, {
      itemId,
      provisional: delta,
      completed: null,
      firstSeenOrder: store.nextOrder,
    })
    return { ...store, items, nextOrder: store.nextOrder + 1 }
  }
  return { ...store, items }
}

export function applyCompleted(store: TranscriptStore, itemId: string, transcript: string): TranscriptStore {
  if (!itemId) return store
  const items = new Map(store.items)
  const existing = items.get(itemId)
  if (existing) {
    // Replace provisional with completed — do not append both.
    items.set(itemId, { ...existing, completed: transcript, provisional: '' })
  } else {
    items.set(itemId, {
      itemId,
      provisional: '',
      completed: transcript,
      firstSeenOrder: store.nextOrder,
    })
    return { ...store, items, nextOrder: store.nextOrder + 1 }
  }
  return { ...store, items }
}

export function itemText(item: TranscriptItem): string {
  if (item.completed != null && item.completed !== '') return item.completed
  return item.provisional
}

export function orderedItems(store: TranscriptStore): TranscriptItem[] {
  return [...store.items.values()].sort((a, b) => a.firstSeenOrder - b.firstSeenOrder)
}

export function liveDraftText(store: TranscriptStore): string {
  const parts = orderedItems(store)
    .map(itemText)
    .map(t => t.trim())
    .filter(Boolean)
  return parts.join('\n\n')
}

export function displayAnswerText(store: TranscriptStore): string {
  const live = liveDraftText(store)
  return [store.finalizedPrevious, live].filter(Boolean).join('\n\n').trim()
}

export function completedRealtimeText(store: TranscriptStore): string {
  const parts = orderedItems(store)
    .map(i => (i.completed != null ? i.completed : '').trim())
    .filter(Boolean)
  return parts.join('\n\n')
}

export function freezeLiveDraft(store: TranscriptStore): string {
  return displayAnswerText(store)
}

export function itemCount(store: TranscriptStore): number {
  return store.items.size
}

export function clearItems(store: TranscriptStore, keepFinalized = true): TranscriptStore {
  return {
    finalizedPrevious: keepFinalized ? store.finalizedPrevious : '',
    items: new Map(),
    nextOrder: 0,
  }
}
