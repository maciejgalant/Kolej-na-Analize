import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
import ts from "typescript";
const source = await readFile(
  new URL("../src/chat/model.ts", import.meta.url),
  "utf8",
);
const js = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
  },
}).outputText;
const {
  initialState,
  appendQuestion,
  activePath,
  analysisContext,
  branchLeaf,
  replaceMessage,
  decodeState,
  validReply,
} = await import(
  "data:text/javascript;base64," + Buffer.from(js).toString("base64")
);
const answered = (c) => ({
  ...c,
  messages: c.messages.map((m) =>
    m.role === "assistant"
      ? { ...m, content: "Odpowiedź", status: undefined }
      : m,
  ),
});

test("editing creates an independent branch without losing the prior continuation", () => {
  const original = appendQuestion(initialState().conversations[0], "Pytanie 1");
  const continued = appendQuestion(
    answered(original.conversation),
    "Pytanie 2",
  );
  const edited = appendQuestion(
    answered(continued.conversation),
    "Nowa wersja",
    undefined,
    original.question.parent,
  );
  assert.deepEqual(
    activePath(edited.conversation).map((m) => m.content),
    ["Nowa wersja", ""],
  );
  assert.deepEqual(
    activePath(
      edited.conversation,
      branchLeaf(edited.conversation, original.question.id),
    ).map((m) => m.content),
    ["Pytanie 1", "Odpowiedź", "Pytanie 2", "Odpowiedź"],
  );
  assert.equal(edited.conversation.messages.length, 6);
});

test("late response modifies its own message without changing active conversation or branch", () => {
  let state = initialState();
  const first = appendQuestion(state.conversations[0], "Pierwsze");
  const second = initialState().conversations[0];
  state = {
    ...state,
    active: second.id,
    conversations: [first.conversation, second],
  };
  const updated = replaceMessage(
    state,
    first.conversation.id,
    first.response.id,
    { status: undefined, content: "Gotowe" },
  );
  assert.equal(updated.active, second.id);
  assert.equal(updated.conversations[1].messages.length, 0);
  assert.equal(updated.conversations[0].messages[1].content, "Gotowe");
  assert.equal(
    replaceMessage(updated, "deleted", first.response.id, { content: "late" })
      .conversations.length,
    2,
  );
});

test("roundtrip preserves tree, context, drafts and per-conversation map state", () => {
  const state = initialState();
  const c = answered(
    appendQuestion(state.conversations[0], "Ruch?", { id: 7, label: "Testowa" })
      .conversation,
  );
  c.map = {
    ...c.map,
    center: [52.2, 21.1],
    zoom: 15,
    category: "B",
    basemap: "ortho",
  };
  c.draft = "Dalsze pytanie";
  state.conversations = [c];
  assert.deepEqual(
    decodeState(JSON.stringify(state)),
    JSON.parse(JSON.stringify(state)),
  );
});

test("reload turns an unfinished response into a recoverable stopped message", () => {
  const state = initialState();
  state.conversations[0] = appendQuestion(
    state.conversations[0],
    "Pytanie",
  ).conversation;
  const loaded = decodeState(JSON.stringify(state));
  assert.equal(loaded.conversations[0].messages[1].status, "stopped");
});

for (const mutation of [
  (s) => {
    s.version = 2;
  },
  (s) => {
    s.conversations[0].map.center = [999, 0];
  },
  (s) => {
    s.active = "missing";
  },
  (s) => {
    s.conversations[0].messages.push({
      id: "cycle",
      parent: "cycle",
      role: "user",
      content: "x",
      created: 1,
    });
  },
]) {
  test("malformed state is rejected instead of silently destroying history", () => {
    const state = initialState();
    mutation(state);
    assert.throws(() => decodeState(JSON.stringify(state)));
  });
}

test("text-only replies stay valid; malformed structured payloads are rejected", () => {
  const reply = { answer: "Opis metody", grounded: false, tool_calls: [] };
  assert.equal(validReply(reply), true);
  assert.equal(validReply({ ...reply, evidence: { cards: null } }), false);
  assert.equal(validReply({ ...reply, tool_calls: [null] }), false);
});

test("new maps default to color and analysis IDs stay on their own branch", () => {
  const c = initialState().conversations[0];
  assert.equal(c.map.basemap, "color");
  const first = appendQuestion(c, "Ranking");
  const scoped = {
    ...first.conversation,
    messages: first.conversation.messages.map((m) =>
      m.id === first.response.id
        ? {
            ...m,
            status: undefined,
            content: "Pięć przejazdów",
            reply: {
              evidence: { map_ids: [5, 2, 8, 9, 3] },
            },
          }
        : m,
    ),
  };
  assert.deepEqual(analysisContext(scoped), [5, 2, 8, 9, 3]);
  const separate = appendQuestion(scoped, "Inna analiza", undefined, null);
  assert.deepEqual(analysisContext(separate.conversation), []);
  assert.deepEqual(analysisContext(c), []);
});
