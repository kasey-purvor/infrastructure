import assert from 'node:assert/strict';
import { extractLinks, htmlToText, normaliseAddress, recipientMatches, unwrapSafeLink, parseDuration } from '../graph-mail.mjs';
assert.equal(normaliseAddress('Agent001+run42@TheCloudAssist.com'), 'agent001@thecloudassist.com');
assert.equal(normaliseAddress('agent001+run42@x.com', false), 'agent001+run42@x.com');
const msg = { toRecipients: [{ emailAddress: { address: 'agent001+ping@thecloudassist.com' } }], ccRecipients: [] };
assert.ok(recipientMatches(msg, 'agent001@thecloudassist.com', true));
assert.ok(!recipientMatches(msg, 'agent001@thecloudassist.com', false));
const wrapped = 'https://eur01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fapp.example.com%2Fverify%3Ftoken%3DabcDEF1234567890abcdef1234&data=05%7C01&reserved=0';
assert.equal(unwrapSafeLink(wrapped), 'https://app.example.com/verify?token=abcDEF1234567890abcdef1234');
const html = `<html><head><style>a{color:red}</style></head><body>
<p>Hi,&nbsp;please <a href="${wrapped}">verify your email</a>.</p>
<p>Or copy: https://app.example.com/verify?token=abcDEF1234567890abcdef1234</p>
<p><a href="https://example.com/unsubscribe">Unsubscribe</a> &middot; <a href="https://twitter.com/x">Twitter</a></p>
</body></html>`;
const links = extractLinks(html);
assert.equal(links[0].url, 'https://app.example.com/verify?token=abcDEF1234567890abcdef1234');
assert.equal(links.length, 3, JSON.stringify(links));
assert.ok(links.at(-1).dropped);
const mc = extractLinks(html, { mustContain: 'twitter.com' });
assert.equal(mc[0].url, 'https://twitter.com/x');
const text = htmlToText(html);
assert.ok(!text.includes('color:red'));
assert.ok(text.includes('verify your email [https://eur01.safelinks'));
assert.equal(parseDuration('5m'), 300000); assert.equal(parseDuration('nope'), null);
console.log('all unit assertions passed');
