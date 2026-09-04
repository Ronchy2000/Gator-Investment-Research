import type { CollectionEntry } from "astro:content";

export type NoteEntry = CollectionEntry<"notes">;

export function sortNotes(notes: NoteEntry[]): NoteEntry[] {
  return [...notes].sort(
    (left, right) => right.data.publishedAt.getTime() - left.data.publishedAt.getTime(),
  );
}

export function noteHref(note: NoteEntry): string {
  return `/notes/${note.id}/`;
}
