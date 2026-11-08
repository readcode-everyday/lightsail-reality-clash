const assert = require('node:assert/strict');
const { test } = require('node:test');
const vm = require('node:vm');
const { applyNode, validateClient } = require('../scripts/configure-clash.cjs');

// Synthetic fixtures only. These values do not grant access to a deployed server.
const fixture = () => ({
  name: 'Demo Reality', type: 'vless', server: '203.0.113.10', port: 443,
  uuid: '00000000-0000-4000-8000-000000000001', servername: 'www.cloudflare.com',
  'reality-opts': { 'public-key': 'A'.repeat(43), 'short-id': '0011223344556677' }
});
const options = { endpointRule: 'IP-CIDR,203.0.113.10/32,DIRECT,no-resolve' };

test('merging retains existing nodes, DNS, custom rules and SSH fallback', () => {
  const originalRules = ['DOMAIN-SUFFIX,local,DIRECT', 'DOMAIN-SUFFIX,example.com,Proxy', 'MATCH,Proxy'];
  const config = { proxies: [{ name: 'SSH', type: 'ssh' }], dns: { enable: true },
    'proxy-groups': [{ name: 'Proxy', type: 'select', proxies: ['SSH'] }], rules: [...originalRules] };
  const result = applyNode(config, validateClient(fixture()), options);
  assert.deepEqual(result.rules.slice(1), originalRules);
  assert.deepEqual(result.dns, { enable: true });
  assert.deepEqual(result['proxy-groups'][0].proxies, ['SSH', 'Demo Reality']);
  assert.equal(result.proxies[0].type, 'ssh');
  assert.equal(result.proxies[1]['reality-opts']['support-x25519mlkem768'], true);
});

test('repeated merges are idempotent and direct suffix routing is opt-in', () => {
  const node = validateClient(fixture());
  const config = applyNode({}, node, options);
  const first = JSON.stringify(config);
  applyNode(config, node, options);
  assert.equal(JSON.stringify(config), first);
  assert.ok(!config.rules.includes('DOMAIN-SUFFIX,gov,DIRECT'));
  applyNode(config, node, { ...options, directCnGov: true });
  assert.deepEqual(config.rules.slice(0, 2), ['DOMAIN-SUFFIX,cn,DIRECT', 'DOMAIN-SUFFIX,gov,DIRECT']);
});

test('explicit groups fail clearly and standalone groups avoid name collisions', () => {
  assert.throws(() => applyNode({}, validateClient(fixture()), { groups: ['Missing'] }), /missing/);
  const node = validateClient({ ...fixture(), name: 'Reality Proxy' });
  const config = applyNode({}, node, options);
  assert.equal(config['proxy-groups'][0].name, 'Reality Proxy 2');
});

test('generated override function runs without Node imports', () => {
  const context = { config: {}, node: validateClient(fixture()), options };
  vm.runInNewContext('result = (' + applyNode.toString() + ')(config, node, options)', context);
  assert.equal(context.result.proxies[0].name, 'Demo Reality');
  assert.equal(context.result.rules.at(-1), 'MATCH,Reality Proxy');
});

test('client export drops unexpected private fields and rejects a server config', () => {
  const node = validateClient({ ...fixture(), privateKey: 'SYNTHETIC_PRIVATE_VALUE' });
  assert.ok(!Object.hasOwn(node, 'privateKey'));
  assert.throws(() => validateClient({ inbounds: [] }), /Expected/);
});
