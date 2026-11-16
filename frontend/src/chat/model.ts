export interface Attachment {
  id: number;
  label: string;
}
export interface MapState {
  center: [number, number];
  zoom: number;
  basemap: "gray" | "color" | "ortho";
  districtId: number | null;
  category: string;
}
export interface ResultCard {
  crossing_id: number;
  title: string;
  district: string | null;
  category: string | null;
  rps: number | null;
  rank: number | null;
  trains: number | null;
}
export interface ResultTable {
  title: string;
  columns: string[];
  rows: (string | number | null)[][];
}
export interface ResultChart {
  title: string;
  unit: string;
  points: { label: string; value: number | null; status: string }[];
}
export interface Evidence {
  presentation?: "full" | "ranking_summary";
  cards: ResultCard[];
  tables: ResultTable[];
  charts: ResultChart[];
  sources: string[];
  notes: string[];
  map_ids: number[];
}
export interface Reply {
  answer: string;
  grounded: boolean;
  tool_calls: {
    name: string;
    arguments: Record<string, unknown>;
    ok: boolean;
  }[];
  evidence?: Evidence;
  disclaimer?: string;
}
export interface Message {
  id: string;
  parent: string | null;
  role: "user" | "assistant";
  content: string;
  created: number;
  attachment?: Attachment;
  reply?: Reply;
  status?: "pending" | "error" | "stopped";
}
export interface Conversation {
  id: string;
  title: string;
  pinned: boolean;
  updated: number;
  messages: Message[];
  leaf: string | null;
  map: MapState;
  draft: string;
  attachment?: Attachment;
}
export interface ChatState {
  version: 1;
  active: string;
  conversations: Conversation[];
}
export const STORAGE_KEY = "railsafe.chat.v1";
export const uid = () => crypto.randomUUID();
export const defaultMap = (): MapState => ({
  center: [52.2297, 21.0122],
  zoom: 11,
  basemap: "color",
  districtId: null,
  category: "",
});
export function newConversation(): Conversation {
  return {
    id: uid(),
    title: "Nowa rozmowa",
    pinned: false,
    updated: Date.now(),
    messages: [],
    leaf: null,
    map: defaultMap(),
    draft: "",
  };
}
export function initialState(): ChatState {
  const c = newConversation();
  return { version: 1, active: c.id, conversations: [c] };
}
export function activePath(c: Conversation, leaf = c.leaf): Message[] {
  const byId = new Map(c.messages.map((m) => [m.id, m]));
  const path: Message[] = [],
    seen = new Set<string>();
  while (leaf && byId.has(leaf) && !seen.has(leaf)) {
    seen.add(leaf);
    const m = byId.get(leaf)!;
    path.unshift(m);
    leaf = m.parent;
  }
  return path;
}

/** Scope follows only the active branch; another conversation cannot contribute IDs. */
export function analysisContext(c: Conversation, parent = c.leaf): number[] {
  const path = activePath(c, parent);
  for (const message of [...path].reverse()) {
    if (
      message.role === "assistant" &&
      !message.status &&
      message.reply?.evidence?.map_ids.length
    ) {
      return [...new Set(message.reply.evidence.map_ids)].slice(0, 15);
    }
  }
  return [];
}
export function branchLeaf(c: Conversation, id: string): string {
  const seen = new Set<string>();
  while (!seen.has(id)) {
    seen.add(id);
    const children = c.messages.filter((m) => m.parent === id);
    if (!children.length) break;
    id = children[children.length - 1].id;
  }
  return id;
}
export function appendQuestion(
  c: Conversation,
  content: string,
  attachment?: Attachment,
  parent = c.leaf,
) {
  const question: Message = {
    id: uid(),
    parent,
    role: "user",
    content,
    attachment,
    created: Date.now(),
  };
  const response: Message = {
    id: uid(),
    parent: question.id,
    role: "assistant",
    content: "",
    status: "pending",
    created: Date.now(),
  };
  return {
    question,
    response,
    conversation: {
      ...c,
      updated: Date.now(),
      draft: "",
      attachment: undefined,
      title: c.messages.length ? c.title : content.slice(0, 55),
      messages: [...c.messages, question, response],
      leaf: response.id,
    },
  };
}
export function replaceMessage(
  state: ChatState,
  conversationId: string,
  messageId: string,
  patch: Partial<Message>,
): ChatState {
  return {
    ...state,
    conversations: state.conversations.map((c) =>
      c.id !== conversationId
        ? c
        : {
            ...c,
            messages: c.messages.map((m) =>
              m.id === messageId ? { ...m, ...patch } : m,
            ),
          },
    ),
  };
}
const obj = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);
const id = (v: unknown): v is number =>
  finite(v) && Number.isInteger(v) && v > 0;
const nullableNumber = (v: unknown) => v === null || finite(v);
const nullableString = (v: unknown) => v === null || typeof v === "string";
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");
function attachment(v: unknown) {
  return v === undefined || (obj(v) && id(v.id) && typeof v.label === "string");
}
export function validEvidence(v: unknown): v is Evidence {
  return (
    obj(v) &&
    Array.isArray(v.cards) &&
    v.cards.every(
      (c) =>
        obj(c) &&
        id(c.crossing_id) &&
        typeof c.title === "string" &&
        nullableString(c.district) &&
        nullableString(c.category) &&
        nullableNumber(c.rps) &&
        nullableNumber(c.rank) &&
        nullableNumber(c.trains),
    ) &&
    Array.isArray(v.tables) &&
    v.tables.every(
      (t) =>
        obj(t) &&
        typeof t.title === "string" &&
        strings(t.columns) &&
        Array.isArray(t.rows) &&
        t.rows.every(
          (r) =>
            Array.isArray(r) &&
            r.length === (t.columns as string[]).length &&
            r.every((x) => x === null || typeof x === "string" || finite(x)),
        ),
    ) &&
    Array.isArray(v.charts) &&
    v.charts.every(
      (c) =>
        obj(c) &&
        typeof c.title === "string" &&
        typeof c.unit === "string" &&
        Array.isArray(c.points) &&
        c.points.every(
          (p) =>
            obj(p) &&
            typeof p.label === "string" &&
            nullableNumber(p.value) &&
            typeof p.status === "string",
        ),
    ) &&
    (v.presentation === undefined ||
      ["full", "ranking_summary"].includes(String(v.presentation))) &&
    strings(v.sources) &&
    strings(v.notes) &&
    Array.isArray(v.map_ids) &&
    v.map_ids.every(id)
  );
}
export function validReply(v: unknown): v is Reply {
  return (
    obj(v) &&
    typeof v.answer === "string" &&
    typeof v.grounded === "boolean" &&
    Array.isArray(v.tool_calls) &&
    v.tool_calls.every(
      (t) =>
        obj(t) &&
        typeof t.name === "string" &&
        obj(t.arguments) &&
        typeof t.ok === "boolean",
    ) &&
    (v.disclaimer === undefined || typeof v.disclaimer === "string") &&
    (v.evidence === undefined || validEvidence(v.evidence))
  );
}
/** Reject malformed/unknown schemas. Caller preserves the original entry on error. */
export function decodeState(raw: string): ChatState {
  const s: unknown = JSON.parse(raw);
  if (
    !obj(s) ||
    s.version !== 1 ||
    typeof s.active !== "string" ||
    !Array.isArray(s.conversations) ||
    !s.conversations.length
  )
    throw Error("Nieznany format historii.");
  const conversationIds = new Set<string>();
  for (const c of s.conversations) {
    if (
      !obj(c) ||
      typeof c.id !== "string" ||
      conversationIds.has(c.id) ||
      typeof c.title !== "string" ||
      typeof c.pinned !== "boolean" ||
      !finite(c.updated) ||
      !Array.isArray(c.messages) ||
      !obj(c.map) ||
      typeof c.draft !== "string" ||
      !attachment(c.attachment)
    )
      throw Error("Uszkodzony zapis rozmów.");
    conversationIds.add(c.id);
    const map = c.map;
    if (
      !Array.isArray(map.center) ||
      map.center.length !== 2 ||
      !map.center.every(finite) ||
      Math.abs(map.center[0]) > 90 ||
      Math.abs(map.center[1]) > 180 ||
      !finite(map.zoom) ||
      map.zoom < 0 ||
      map.zoom > 22 ||
      !["gray", "color", "ortho"].includes(String(map.basemap)) ||
      !(map.districtId === null || id(map.districtId)) ||
      !["", "A", "B", "C", "D", "E", "F"].includes(String(map.category))
    )
      throw Error("Uszkodzony zapis mapy.");
    const messages = new Map<string, string>();
    for (const m of c.messages) {
      if (
        !obj(m) ||
        typeof m.id !== "string" ||
        messages.has(m.id) ||
        !(m.parent === null
          ? m.role === "user"
          : typeof m.parent === "string" &&
            messages.has(m.parent) &&
            messages.get(m.parent) !== m.role) ||
        !["user", "assistant"].includes(String(m.role)) ||
        typeof m.content !== "string" ||
        !finite(m.created) ||
        !attachment(m.attachment) ||
        (m.reply !== undefined && !validReply(m.reply)) ||
        (m.status !== undefined &&
          !["pending", "error", "stopped"].includes(String(m.status)))
      )
        throw Error("Uszkodzona gałąź rozmowy.");
      messages.set(m.id, String(m.role));
      if (m.status === "pending") {
        m.status = "stopped";
        m.content =
          "Oczekiwanie przerwane po ponownym otwarciu aplikacji. Możesz ponowić odpowiedź.";
      }
    }
    if (
      !(c.leaf === null || (typeof c.leaf === "string" && messages.has(c.leaf)))
    )
      throw Error("Brak aktywnej gałęzi.");
  }
  if (!conversationIds.has(s.active)) throw Error("Brak aktywnej rozmowy.");
  return s as unknown as ChatState;
}
