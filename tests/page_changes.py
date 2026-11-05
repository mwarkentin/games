"""Find DOM writes that keep setting what's already there.

Setting text, or an attribute such as `hidden` or `disabled`, is a DOM change
even when the value doesn't change. Done on every animation frame, it makes
anything that watches the page for changes, such as a session replay
recorder, do work 60 times a second for nothing. Only write what changed,
as setText() in Funnels & Buckets and Air Traffic Controller does for text.
"""

from __future__ import annotations

from playwright.sync_api import Page

# Resolves to {"<what> on <element>": count} for writes that left the value
# as it was, over the given milliseconds. Each element counts on its own.
NO_OP_WRITES_JS = """(ms) => new Promise((done) => {
  const label = (n) => n.nodeType === 3 ? label(n.parentNode)
    : n.id ? '#' + n.id
    : !n.parentElement ? n.tagName.toLowerCase()
    : `${label(n.parentElement)} > ${n.tagName.toLowerCase()}:nth-child(${[...n.parentElement.children].indexOf(n) + 1})`;
  const html = new Map([...document.querySelectorAll('*')].map((el) => [el, el.innerHTML]));
  const counts = {};
  const count = (what, node) => { const key = `${what} on ${label(node)}`; counts[key] = (counts[key] || 0) + 1; };
  const observer = new MutationObserver((records) => {
    const rewritten = new Set();
    for (const r of records) {
      if (r.type === 'childList') rewritten.add(r.target);
      else if (r.type === 'characterData' && r.oldValue === r.target.data) count('text', r.target);
      else if (r.type === 'attributes' && r.oldValue === r.target.getAttribute(r.attributeName)) count(r.attributeName, r.target);
    }
    for (const el of rewritten) {
      if (html.get(el) === el.innerHTML) count('content', el);
      html.set(el, el.innerHTML);
    }
  });
  observer.observe(document, {
    subtree: true, childList: true, attributes: true, characterData: true,
    attributeOldValue: true, characterDataOldValue: true,
  });
  setTimeout(() => { observer.disconnect(); done(counts); }, ms);
})"""


def repeated_no_op_writes(page: Page, seconds: float = 3) -> dict[str, int]:
    """Elements set to the value they already had at least once a second.

    Air Traffic Controller redraws its panels once per tick, every 2.5 s or
    more, which stays under that: two writes to an element in 3 seconds at most.
    """
    counts = page.evaluate(NO_OP_WRITES_JS, seconds * 1000)
    return {key: n for key, n in counts.items() if n >= seconds}
