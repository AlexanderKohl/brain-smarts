'use strict';
// Small questions the JavaScript extractor asks of a syntax node.
// Moved unchanged from extract.js. extract.js loads these names back, so its callers see the same names.
const A = require('./ast');

function jsxName(node) {
  if (!node) return null;
  if (node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'JSXMemberExpression') return `${jsxName(node.object)}.${node.property.name}`;
  return null;
}

// A binding that holds a whole imported module: require('./m'), import * as m, or a default import.
function wholeImport(b) {
  return !!b && !!b.import && !b.import.member && (b.import.imported === '*' || b.import.imported === 'default');
}

function isEnvObject(node) {
  node = A.unwrap(node);
  if (!A.isMember(node)) return false;
  const obj = A.unwrap(node.object);
  const prop = A.keyName(node.property, node.computed);
  if (prop !== 'env') return false;
  if (obj.type === 'Identifier' && obj.name === 'process') return true;
  return obj.type === 'MetaProperty' && obj.meta.name === 'import' && obj.property.name === 'meta';
}

function isReference(node, parent, key) {
  if (!parent) return true;
  switch (parent.type) {
    case 'MemberExpression':
    case 'OptionalMemberExpression': return key !== 'property' || parent.computed;
    case 'ObjectProperty': return key === 'value' || parent.computed;
    case 'ObjectMethod':
    case 'ClassMethod':
    case 'ClassPrivateMethod':
    case 'ClassProperty': return key !== 'key' || parent.computed;
    case 'VariableDeclarator': return key === 'init';
    case 'FunctionDeclaration':
    case 'FunctionExpression':
    case 'ArrowFunctionExpression': return key === 'body';
    case 'ImportSpecifier':
    case 'ImportDefaultSpecifier':
    case 'ImportNamespaceSpecifier':
    case 'ExportSpecifier':
    case 'LabeledStatement':
    case 'BreakStatement':
    case 'ContinueStatement':
    case 'MetaProperty':
    case 'ClassDeclaration':
    case 'ClassExpression': return key === 'superClass';
    case 'CatchClause': return key !== 'param';
    default: return true;
  }
}

module.exports = { jsxName, wholeImport, isEnvObject, isReference };
