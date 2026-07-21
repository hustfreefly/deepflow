/**
 * Unit tests for config.ts — configuration loading, merging, and validation.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import {
  loadConfig,
  substituteEnvVars,
  substituteEnvVarsDeep,
  parseDuration,
  DEFAULTS,
} from '../src/config';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createTempYaml(content: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'deepflow-test-'));
  const filePath = path.join(dir, 'deepflow.yaml');
  fs.writeFileSync(filePath, content, 'utf8');
  return filePath;
}

// ---------------------------------------------------------------------------
// substituteEnvVars
// ---------------------------------------------------------------------------

describe('substituteEnvVars', () => {
  beforeEach(() => {
    process.env['TEST_VAR'] = 'hello';
    process.env['TEST_PORT'] = '8080';
    delete process.env['TEST_MISSING'];
  });

  afterEach(() => {
    delete process.env['TEST_VAR'];
    delete process.env['TEST_PORT'];
    delete process.env['TEST_MISSING'];
  });

  it('should replace ${VAR} with env value', () => {
    expect(substituteEnvVars('${TEST_VAR}')).toBe('hello');
  });

  it('should use default value when env var missing', () => {
    expect(substituteEnvVars('${TEST_MISSING:-world}')).toBe('world');
  });

  it('should throw when env var missing and no default', () => {
    expect(() => substituteEnvVars('${TEST_MISSING}')).toThrow(
      /TEST_MISSING/
    );
  });

  it('should handle multiple substitutions in one string', () => {
    expect(substituteEnvVars('${TEST_VAR}:${TEST_PORT}')).toBe('hello:8080');
  });

  it('should not affect strings without substitution patterns', () => {
    expect(substituteEnvVars('plain string')).toBe('plain string');
  });
});

// ---------------------------------------------------------------------------
// substituteEnvVarsDeep
// ---------------------------------------------------------------------------

describe('substituteEnvVarsDeep', () => {
  beforeEach(() => {
    process.env['DEEP_VAR'] = 'deep_value';
  });

  afterEach(() => {
    delete process.env['DEEP_VAR'];
  });

  it('should recursively substitute in nested objects', () => {
    const input = {
      sdk: { service_name: '${DEEP_VAR}' },
      vault: { address: 'https://${DEEP_VAR}:8200' },
    };
    const result = substituteEnvVarsDeep(input) as typeof input;
    expect(result.sdk.service_name).toBe('deep_value');
    expect(result.vault.address).toBe('https://deep_value:8200');
  });

  it('should handle arrays', () => {
    const input = ['${DEEP_VAR}', 'static'];
    const result = substituteEnvVarsDeep(input) as string[];
    expect(result[0]).toBe('deep_value');
    expect(result[1]).toBe('static');
  });
});

// ---------------------------------------------------------------------------
// parseDuration
// ---------------------------------------------------------------------------

describe('parseDuration', () => {
  it('should parse milliseconds', () => {
    expect(parseDuration('500ms')).toBe(500);
  });

  it('should parse seconds', () => {
    expect(parseDuration('30s')).toBe(30000);
  });

  it('should parse minutes', () => {
    expect(parseDuration('5m')).toBe(300000);
  });

  it('should parse hours', () => {
    expect(parseDuration('1h')).toBe(3600000);
  });

  it('should throw on invalid format', () => {
    expect(() => parseDuration('5x')).toThrow('Invalid duration format');
    expect(() => parseDuration('abc')).toThrow('Invalid duration format');
    expect(() => parseDuration('')).toThrow('Invalid duration format');
  });
});

// ---------------------------------------------------------------------------
// loadConfig
// ---------------------------------------------------------------------------

describe('loadConfig', () => {
  it('should return defaults when no config file exists', () => {
    const config = loadConfig({ configPath: '/nonexistent/config.yaml', envPrefix: 'DEEPFLOW_' });
    expect(config.sdk.service_name).toBe('deepflow-service');
    expect(config.sdk.environment).toBe('production');
    expect(config.vault.enabled).toBe(false);
    expect(config.strict_mode).toBe(true);
  });

  it('should load and merge YAML config with defaults', () => {
    const yamlContent = `
sdk:
  service_name: test-service
  environment: development
`;
    const yamlPath = createTempYaml(yamlContent);
    const config = loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' });

    expect(config.sdk.service_name).toBe('test-service');
    expect(config.sdk.environment).toBe('development');
    // Defaults should still be present
    expect(config.sdk.log_level).toBe('info');
    expect(config.vault.enabled).toBe(false);
    expect(config.tls.enabled).toBe(false);
  });

  it('should apply env variable overrides', () => {
    process.env['DEEPFLOW_SDK_SERVICE_NAME'] = 'env-override-service';
    const yamlContent = `
sdk:
  service_name: yaml-service
`;
    const yamlPath = createTempYaml(yamlContent);
    const config = loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' });

    expect(config.sdk.service_name).toBe('env-override-service');

    delete process.env['DEEPFLOW_SDK_SERVICE_NAME'];
  });

  it('should throw on missing required fields', () => {
    const yamlContent = `
sdk:
  service_name: ""
`;
    const yamlPath = createTempYaml(yamlContent);
    expect(() => loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' })).toThrow(
      /service_name is required/
    );
  });

  it('should throw on invalid environment enum', () => {
    const yamlContent = `
sdk:
  service_name: test
  environment: invalid
`;
    const yamlPath = createTempYaml(yamlContent);
    expect(() => loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' })).toThrow(
      /environment must be one of/
    );
  });

  it('should throw on invalid duration format', () => {
    const yamlContent = `
sdk:
  service_name: test
vault:
  renewal_interval: 5x
`;
    const yamlPath = createTempYaml(yamlContent);
    expect(() => loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' })).toThrow(
      /invalid duration format/i
    );
  });

  it('should validate Vault AppRole conditional requirements', () => {
    const yamlContent = `
sdk:
  service_name: test
vault:
  enabled: true
  auth_method: approle
`;
    const yamlPath = createTempYaml(yamlContent);
    expect(() => loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' })).toThrow(
      /approle/
    );
  });

  it('should validate Vault Token conditional requirements', () => {
    const yamlContent = `
sdk:
  service_name: test
vault:
  enabled: true
  auth_method: token
`;
    const yamlPath = createTempYaml(yamlContent);
    expect(() => loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' })).toThrow(
      /token/
    );
  });

  it('should handle env var substitution in YAML values', () => {
    process.env['TEST_SERVICE'] = 'substituted-service';
    const yamlContent = [
      'sdk:',
      '  service_name: "${TEST_SERVICE}"',
    ].join('\n');
    const yamlPath = createTempYaml(yamlContent);
    const config = loadConfig({ configPath: yamlPath, envPrefix: 'DEEPFLOW_' });
    expect(config.sdk.service_name).toBe('substituted-service');
    delete process.env['TEST_SERVICE'];
  });
});

// ---------------------------------------------------------------------------
// DEFAULTS
// ---------------------------------------------------------------------------

describe('DEFAULTS', () => {
  it('should have all required sections', () => {
    expect(DEFAULTS.sdk).toBeDefined();
    expect(DEFAULTS.vault).toBeDefined();
    expect(DEFAULTS.tls).toBeDefined();
    expect(DEFAULTS.otel).toBeDefined();
    expect(DEFAULTS.health).toBeDefined();
    expect(DEFAULTS.strict_mode).toBe(true);
  });

  it('should have valid default enum values', () => {
    expect(DEFAULTS.sdk.environment).toBe('production');
    expect(DEFAULTS.sdk.log_level).toBe('info');
    expect(DEFAULTS.vault.auth_method).toBe('approle');
    expect(DEFAULTS.otel.protocol).toBe('grpc');
  });
});