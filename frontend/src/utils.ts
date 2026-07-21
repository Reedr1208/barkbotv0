import { Dog, SITE_URL } from './api';

/**
 * Resolve a dog's display image, mirroring the web fallback order:
 * image_base_url + image_file  ->  image_public_url  ->  shelter_image_url.
 */
export function resolveDogImage(dog: Partial<Dog>): string | undefined {
  if (dog.image_base_url && dog.image_file) {
    return `${dog.image_base_url}${dog.image_file}`;
  }
  if (dog.image_public_url) return dog.image_public_url;
  if (dog.shelter_image_url) return dog.shelter_image_url;
  return undefined;
}

/** Human-friendly "last checked" line from an ISO timestamp. */
export function freshnessLabel(iso?: string): string {
  if (!iso) return 'recently';
  const then = new Date(iso);
  if (isNaN(then.getTime())) return 'recently';
  const now = new Date();
  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Relative time for conversation rows ("2h ago", "3d ago"). */
export function relativeTime(iso?: string): string {
  if (!iso) return '';
  const then = new Date(iso);
  if (isNaN(then.getTime())) return '';
  const secs = Math.floor((Date.now() - then.getTime()) / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** True when the dog satisfied at least one active preference. */
export function isStrongMatch(dog: Dog): boolean {
  if (dog.preferences_matched) return true;
  const d = dog.match_details;
  if (!d) return false;
  return Object.values(d).some((m) => m && m.active && m.matched);
}

/** Capitalize a free-form attribute value for chips. */
export function titleCase(value?: string): string {
  if (!value) return '—';
  return value
    .split(' ')
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ');
}

export function dogSex(dog: Dog): string {
  const v = dog.sex || dog.gender;
  if (!v) return '—';
  const lower = v.toLowerCase();
  if (lower.startsWith('m')) return 'Male';
  if (lower.startsWith('f')) return 'Female';
  return titleCase(v);
}

export function dogAge(dog: Dog): string {
  return dog.age_summary || dog.age || titleCase(dog.age_bucket) || '—';
}

export function dogWeight(dog: Dog): string {
  return dog.weight_summary || dog.weight || titleCase(dog.weight_class) || '—';
}

/** Collect personality trait pills from the various enriched arrays. */
export function dogTraits(dog: Dog, max = 6): string[] {
  const pool = [...(dog.strengths || []), ...(dog.important_facts || [])];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of pool) {
    const trimmed = (t || '').trim();
    if (trimmed && !seen.has(trimmed.toLowerCase())) {
      seen.add(trimmed.toLowerCase());
      out.push(trimmed);
    }
    if (out.length >= max) break;
  }
  return out;
}

/** The best available biography text. */
export function dogBio(dog: Dog): string {
  return (dog.bio || dog.description || dog.intro_summary || '').trim();
}

/** Public canonical URL for a dog (used for sharing & deep links). */
export function dogShareUrl(animalId: string): string {
  return `${SITE_URL}/dogs/${encodeURIComponent(animalId)}`;
}

/** Friendly, human share copy that matches the site's tone. */
export function dogShareMessage(name: string, animalId: string): string {
  const who = name && name !== 'this dog' ? name : 'this adoptable dog';
  return `Meet ${who} on ChattyHound 🐶\nI found this adoptable dog and thought of you.\n${dogShareUrl(
    animalId
  )}`;
}

/** Suggested chat prompts, personalized to the dog (mirrors the web). */
export function quickPrompts(name: string): string[] {
  const who = name && name !== 'this dog' ? name : 'this pup';
  return [
    `What home fits ${who} best?`,
    `Is ${who} good with kids?`,
    `What should I know before meeting ${who}?`,
  ];
}
