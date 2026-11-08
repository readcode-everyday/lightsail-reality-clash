#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { parseArgs } = require('node:util');
const YAML = require('yaml');

function validateClient(value) {
  if (!value || value.type !== 'vless' || !value.name || !value.server ||
      !Number.isInteger(value.port) || value.port < 1 || value.port > 65535 ||
      !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.uuid || '')) {
    throw new Error('Expected the generated VLESS client JSON with a valid endpoint and UUID');
  }
  if (!net.isIP(value.server) && !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(value.server)) {
    throw new Error('Server must be an IP address or hostname');
  }
  const reality = value['reality-opts'];
  if (!reality || !/^[A-Za-z0-9_-]{43}$/.test(reality['public-key'] || '') ||
      !/^(?:[0-9a-f]{2}){1,8}$/i.test(reality['short-id'] || '') || !value.servername) {
    throw new Error('Missing valid REALITY public key, short ID, or server name');
  }
  // Whitelist client fields so a mistakenly supplied server config is never copied.
  return {
    name: String(value.name), type: 'vless', server: value.server, port: value.port,
    uuid: value.uuid, flow: 'xtls-rprx-vision', tls: true, servername: value.servername,
    'client-fingerprint': 'chrome', udp: true, 'packet-encoding': 'xudp',
    'reality-opts': { 'public-key': reality['public-key'], 'short-id': reality['short-id'],
                      'support-x25519mlkem768': true }
  };
}

// Deliberately self-contained: this function is also embedded in Clash Party overrides.
function applyNode(config, node, options) {
  config.proxies = (config.proxies || []).filter(item => item.name !== node.name).concat([node]);
  const groups = config['proxy-groups'] || [];
  const names = options.groups || [];
  let targets;
  if (names.length) {
    targets = names.map(name => {
      const group = groups.find(item => item.name === name && item.type === 'select');
      if (!group) throw new Error('Requested select group is missing: ' + name);
      return group;
    });
  } else {
    const selectors = groups.filter(item => item.type === 'select' && !/direct|直连|reject/i.test(item.name));
    targets = selectors.filter(item => /proxy|proxies|^ai$|节点选择|代理选择/i.test(item.name));
    if (!targets.length && selectors.length) targets = [selectors[0]];
  }
  if (!targets.length) {
    const occupied = new Set(groups.concat(config.proxies).map(item => item.name));
    let name = 'Reality Proxy';
    for (let index = 2; occupied.has(name); index++) name = 'Reality Proxy ' + index;
    const group = { name, type: 'select', proxies: [] };
    groups.push(group);
    targets = [group];
  }
  config['proxy-groups'] = groups;
  for (const group of targets) {
    group.proxies = group.proxies || [];
    if (!group.proxies.includes(node.name)) group.proxies.push(node.name);
  }
  const prefix = options.directCnGov ? ['DOMAIN-SUFFIX,cn,DIRECT', 'DOMAIN-SUFFIX,gov,DIRECT'] : [];
  if (options.endpointRule && !(config.rules || []).includes(options.endpointRule)) prefix.push(options.endpointRule);
  const rules = config.rules || [];
  config.rules = prefix.concat(rules.filter(rule => !prefix.includes(rule)));
  if (!config.rules.some(rule => rule.startsWith('MATCH,'))) {
    config.rules.push('MATCH,' + targets[0].name);
  }
  return config;
}

function writePrivate(filename, content) {
  const directory = path.dirname(path.resolve(filename));
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (fs.existsSync(filename)) {
    const backup = filename + '.bak.' + Date.now();
    fs.copyFileSync(filename, backup, fs.constants.COPYFILE_EXCL);
    fs.chmodSync(backup, 0o600);
  }
  const temporary = path.join(directory, '.reality-' + require('node:crypto').randomBytes(12).toString('hex'));
  try {
    fs.writeFileSync(temporary, content, { flag: 'wx', mode: 0o600 });
    fs.renameSync(temporary, filename);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function main() {
  const { values } = parseArgs({ options: {
    client: { type: 'string' }, input: { type: 'string' }, output: { type: 'string' },
    'override-output': { type: 'string' }, group: { type: 'string', multiple: true },
    'direct-cn-gov': { type: 'boolean', default: false }, help: { type: 'boolean' }
  }});
  if (values.help) {
    console.log('node scripts/configure-clash.cjs --client private/client.json [--input private/profile.yaml] --output generated/profile.yaml [--group NAME] [--direct-cn-gov]\nUse --override-output generated/reality.js to generate a Clash Party JavaScript override.');
    return;
  }
  if (!values.client || (!values.output && !values['override-output'])) {
    throw new Error('--client and either --output or --override-output are required');
  }
  if (values.input && values.output && path.resolve(values.input) === path.resolve(values.output)) {
    throw new Error('Choose a separate output file; the source profile is kept intact');
  }
  const node = validateClient(JSON.parse(fs.readFileSync(values.client, 'utf8')));
  const family = net.isIP(node.server);
  const options = {
    groups: values.group || [], directCnGov: values['direct-cn-gov'],
    endpointRule: family ? `${family === 4 ? 'IP-CIDR' : 'IP-CIDR6'},${node.server}/${family === 4 ? 32 : 128},DIRECT,no-resolve` : null
  };
  if (values.output) {
    const config = values.input ? YAML.parse(fs.readFileSync(values.input, 'utf8')) :
      { 'mixed-port': 7890, 'allow-lan': false, mode: 'rule', 'log-level': 'info', ipv6: false };
    if (!config || typeof config !== 'object' || Array.isArray(config)) throw new Error('Expected a YAML profile object');
    writePrivate(values.output, YAML.stringify(applyNode(config, node, options)));
    console.log('Saved profile: ' + values.output);
  }
  if (values['override-output']) {
    const script = '// Generated locally; contains access credentials. Keep private.\nfunction main(config) {\n' +
      'return (' + applyNode.toString() + ')(config, ' + JSON.stringify(node) + ', ' + JSON.stringify(options) + ');\n}\n';
    writePrivate(values['override-output'], script);
    console.log('Saved override: ' + values['override-output']);
  }
}

module.exports = { validateClient, applyNode };
if (require.main === module) {
  try { main(); } catch (error) { console.error('Error: ' + error.message); process.exitCode = 1; }
}
