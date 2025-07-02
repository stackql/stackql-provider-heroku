#!/usr/bin/env python3
import yaml
import json
import os
import re
from urllib.parse import unquote

INPUT_SCHEMA_FILE = 'schema.json'
PROVIDER_NAME = 'heroku'
VERSION = 'v0'
OUTPUT_DIR = os.path.join('provider', PROVIDER_NAME, VERSION)
SERVICES_DIR = os.path.join(OUTPUT_DIR, 'services')

# Heroku's schema has over 100 resources and a lot of them are connected, they will be mapped together
# into a smaller set of files. (E.G., 'app' AND 'team-app' both go into 'apps.yaml').
RESOURCE_SERVICE_MAP = {
    'app': 'apps', 'team-app': 'apps', 'app-feature': 'apps', 'app-setup': 'apps', 'app-transfer': 'apps',
    'app-webhook': 'apps', 'app-webhook-delivery': 'apps', 'app-webhook-event': 'apps',
    'addon': 'addons', 'add-on': 'addons', 'add-on-attachment': 'addons', 'add-on-service': 'addons',
    'plan': 'addons', 'allowed-add-on-service': 'addons', 'add-on-config': 'addons', 'add-on-action': 'addons',
    'build': 'builds', 'buildpack-installation': 'builds',
    'config-var': 'config_vars',
    'dyno': 'dynos', 'dyno-size': 'dynos', 'formation': 'dynos',
    'log-drain': 'logging', 'log-session': 'logging',
    'release': 'releases', 'slug': 'releases', 'oci-image': 'releases',
    'account': 'accounts', 'account-feature': 'accounts',
    'team': 'teams', 'team-member': 'teams', 'team-invitation': 'teams', 'team-feature': 'teams',
    'collaborator': 'collaborators', 'team-app-collaborator': 'collaborators',
    'domain': 'domains', 'sni-endpoint': 'domains',
    'key': 'keys',
    'oauth-authorization': 'oauth', 'oauth-client': 'oauth', 'oauth-token': 'oauth', 'oauth-grant': 'oauth',
    'pipeline': 'pipelines', 'pipeline-coupling': 'pipelines', 'pipeline-promotion': 'pipelines',
    'pipeline-release': 'pipelines', 'pipeline-deployment': 'pipelines',
    'region': 'platform', 'stack': 'platform',
    'space': 'spaces', 'vpn-connection': 'networking', 'peering': 'networking',
    'default': 'misc'
}

def sanitize_name(name, capitalize=False):
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    name = name.strip('_')
    if capitalize:
        return "".join(word.capitalize() for word in name.split('_'))
    return name

def get_service_name_for_resource(resource_name):
    return RESOURCE_SERVICE_MAP.get(resource_name, 'misc')

def create_base_spec(service_name, heroku_schema):
    """Generates boilerplate"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": f"Heroku Platform API - {service_name.replace('_', ' ').title()}",
            "description": heroku_schema.get('description', f"Operations related to Heroku {service_name}."),
            "version": VERSION
        },
        "servers": [{"url": "https://api.heroku.com"}],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {
                "herokuAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "API Key"}
            }
        },
        "security": [{"herokuAuth": []}]
    }

def clean_schema_object(obj):
    """Removes non-OpenAPI keys from a schema object that would otherwise make the final specification invalid"""
    if not isinstance(obj, dict):
        return
    invalid_keys = ['links', 'definitions', 'stability', 'strictProperties', '$schema', 'title', 'example']
    for key in invalid_keys:
        if key in obj:
            del obj[key]
    
    for key in list(obj.keys()):
        if isinstance(obj[key], (dict, list)):
            # remove all nested invalid keys with recursion
            clean_schema_object(obj[key])

def rewrite_refs_recursive(obj, service_spec, heroku_schema):
    """Rewrites internal references in valid OpenAPI"""
    """find every $ref, locate the original definition it points to, copy that definition to the correct
    central location (/components/schemas/), and then update the $ref to point to that new location."""
    if isinstance(obj, dict):
        if '$ref' in obj and obj['$ref'].startswith('#/definitions/'):
            original_ref = obj['$ref']
            parts = original_ref.split('/')
            
            # Case 1: #/definitions/resource/definitions/schema
            if len(parts) >= 5 and parts[3] == 'definitions':
                resource_name = parts[2]
                schema_name = parts[4]
                if schema_name not in service_spec['components']['schemas']:
                    if resource_name in heroku_schema['definitions'] and \
                       'definitions' in heroku_schema['definitions'][resource_name] and \
                       schema_name in heroku_schema['definitions'][resource_name]['definitions']:
                        # original schema object
                        schema_def = heroku_schema['definitions'][resource_name]['definitions'][schema_name]
                        service_spec['components']['schemas'][schema_name] = schema_def
                        clean_schema_object(service_spec['components']['schemas'][schema_name])
                        rewrite_refs_recursive(service_spec['components']['schemas'][schema_name], service_spec, heroku_schema)
                obj['$ref'] = f"#/components/schemas/{schema_name}"
            # Case 2: #/definitions/resource
            else:
                schema_name = parts[-1]
                if schema_name not in service_spec['components']['schemas']:
                     if schema_name in heroku_schema['definitions']:
                        schema_def = dict(heroku_schema['definitions'][schema_name])
                        service_spec['components']['schemas'][schema_name] = schema_def
                        clean_schema_object(service_spec['components']['schemas'][schema_name])
                        rewrite_refs_recursive(service_spec['components']['schemas'][schema_name], service_spec, heroku_schema)
                obj['$ref'] = f"#/components/schemas/{schema_name}"
        
        for key, value in list(obj.items()):
            rewrite_refs_recursive(value, service_spec, heroku_schema)

    elif isinstance(obj, list):
        for item in obj:
            rewrite_refs_recursive(item, service_spec, heroku_schema)

def map_rel_to_sql_verb(rel):
    """Translate to a corresponding SQL verb"""
    if rel in ["instances", "self"]: return "select"
    if rel == "create": return "insert"
    if rel == "update": return "update"
    if rel in ["destroy", "delete"]: return "delete"
    return "exec"

def process_heroku_schema():
    with open(INPUT_SCHEMA_FILE, 'r') as f:
        heroku_schema = json.load(f)

    service_specs = {}

    for resource_name, resource_def in heroku_schema['definitions'].items():
        service_name = get_service_name_for_resource(resource_name)
        if service_name not in service_specs:
            service_specs[service_name] = create_base_spec(service_name, heroku_schema)
        spec = service_specs[service_name]
        
        if 'links' not in resource_def:
            continue
            
        for link in resource_def['links']:
            path_params = []
            path = unquote(link['href'])
            
            def repl(m):
                # Generate a more unique parameter name
                # OpenAPI: every parameter in a given path must have a unique name
                pointer = m.group(1)
                base_name = pointer.split('/')[-1].replace(')','').replace('(','')
                resource_context = pointer.split('/')[2] if len(pointer.split('/')) > 2 else base_name
                param_name = sanitize_name(f"{resource_context}_{base_name}")
                
                # Avoid creating duplicate parameter objects for the same path
                if not any(p['name'] == param_name for p in path_params):
                    path_params.append({
                        "name": param_name, "in": "path", "required": True,
                        "schema": {"type": "string"}, "description": f"Unique identifier for {base_name} of {resource_context}."
                    })
                return f"{{{param_name}}}"

            path = re.sub(r'{\(([^)]+)\)}', repl, path)
            
            method = link['method'].lower()
            op_title = sanitize_name(link.get('title', link.get('rel', 'untitled')), capitalize=True)
    
            operation = {
                "summary": link.get('title', 'No summary provided'),
                "description": link.get('description', ''),
                "operationId": f"{sanitize_name(resource_name)}{op_title}",
                "tags": [service_name],
                "parameters": path_params,
                "responses": {},
                "x-stackQL-resource": resource_name,
                "x-stackQL-method": op_title,
                "x-stackQL-verb": map_rel_to_sql_verb(link.get('rel', 'exec'))
            }

            if 'schema' in link:
                operation['requestBody'] = {"required": True, "content": {"application/json": {"schema": link['schema']}}}

            status_code = '200'
            if method == 'post' and link.get('rel') == 'create': status_code = '201'
            elif method == 'delete': status_code = '204'

            description = "Successful operation"
            if status_code == '201': description = "Created"
            if status_code == '204': description = "No Content"

            if 'targetSchema' in link and status_code != '204':
                operation['responses'][status_code] = {"description": description, "content": {"application/json": {"schema": link['targetSchema']}}}
            else:
                 operation['responses'][status_code] = {"description": description}

            if path not in spec['paths']: spec['paths'][path] = {}
            spec['paths'][path][method] = operation

    for service_name, spec in service_specs.items():
        # fix all references
        rewrite_refs_recursive(spec, spec, heroku_schema)
        
        # bulid the x-stackQL-references block
        resources = {}
        for path, path_obj in spec['paths'].items():
            for verb, op in path_obj.items():
                res_name, meth_name, sql_verb = op['x-stackQL-resource'], op['x-stackQL-method'], op['x-stackQL-verb']
                if res_name not in resources:
                    resources[res_name] = {
                        "id": f"{PROVIDER_NAME}.{service_name}.{res_name}", "name": res_name, "title": res_name.replace('-', ' ').title(),
                        "methods": {}, "sqlVerbs": {"select": [], "insert": [], "update": [], "delete": [], "exec": []}
                    }
                
                path_ref = path.replace("/", "~1")
                resources[res_name]['methods'][meth_name] = {
                    "operation": {"$ref": f"#/paths/{path_ref}/{verb}"},
                    "response": {"mediaType": "application/json", "openAPIDocKey": next(iter(op['responses']))}
                }
                
                method_ref = f"#/components/x-stackQL-resources/{res_name}/methods/{meth_name}"
                if sql_verb in resources[res_name]['sqlVerbs']:
                    resources[res_name]['sqlVerbs'][sql_verb].append({"$ref": method_ref})

        spec['components']['x-stackQL-resources'] = resources

    # write all files
    os.makedirs(SERVICES_DIR, exist_ok=True)
    for service_name, spec in service_specs.items():
        output_path = os.path.join(SERVICES_DIR, f"{service_name}.yaml")
        with open(output_path, 'w') as f:
            yaml.dump(spec, f, sort_keys=False, default_flow_style=False, width=120)

    # generate provider
    provider_manifest = {
        "id": PROVIDER_NAME, "name": PROVIDER_NAME, "version": VERSION,
        "providerServices": {},
        "config": {"auth": {"type": "bearer", "credentialsenvvar": "HEROKU_API_TOKEN"}}
    }
    for service_name in sorted(service_specs.keys()):
        provider_manifest['providerServices'][service_name] = {
            "id": f"{service_name}:{VERSION}", "name": service_name, "preferred": True,
            "service": {"$ref": f"{PROVIDER_NAME}/{VERSION}/services/{service_name}.yaml"},
            "title": f"Heroku {service_name.replace('_', ' ').title()}",
            "version": VERSION, "description": service_specs[service_name]['info']['description']
        }
    
    manifest_path = os.path.join(OUTPUT_DIR, 'provider.yaml')
    with open(manifest_path, 'w') as f:
        yaml.dump(provider_manifest, f, sort_keys=False, default_flow_style=False, width=120)


if __name__ == "__main__":
    process_heroku_schema()