Title: GitHub - eyereasoner/eye-js: A distribution of EYE reasoner in the JavaScript ecosystem using Webassembly.

URL Source: https://github.com/eyereasoner/eye-js/

Markdown Content:
EYE JS
------

[](https://github.com/eyereasoner/eye-js/#eye-js)

Distributing the [EYE](https://github.com/eyereasoner/eye) reasoner for browser and node using WebAssembly.

[![Image 1: GitHub license](https://camo.githubusercontent.com/7f0908e60d7c102c709a05939c22c2943425a9cff8ff4b9acb6b2d664ba95d3b/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f6c6963656e73652f657965726561736f6e65722f6579652d6a732e737667)](https://github.com/eyereasoner/eye-js/blob/master/LICENSE) [![Image 2: npm version](https://camo.githubusercontent.com/0b1a2e6f7b467bb9aa140fc50a1a4acdefe4b3eb83e6b79bd33b279c1ff9ca6f/68747470733a2f2f696d672e736869656c64732e696f2f6e706d2f762f657965726561736f6e65722e737667)](https://www.npmjs.com/package/eyereasoner) [![Image 3: build](https://camo.githubusercontent.com/70fd9ecd297bf90405278d2f418ff4b1e3d6d786d5fab95960ebe9f365afe368/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f616374696f6e732f776f726b666c6f772f7374617475732f657965726561736f6e65722f6579652d6a732f6e6f64656a732e796d6c3f6272616e63683d6d61696e)](https://github.com/eyereasoner/eye-js/tree/main/) [![Image 4: Dependabot](https://camo.githubusercontent.com/8acb8e1327c260658912108affc90bca9395bad094fef9b054c0773c5c275f31/68747470733a2f2f62616467656e2e6e65742f62616467652f446570656e6461626f742f656e61626c65642f677265656e3f69636f6e3d646570656e6461626f74)](https://dependabot.com/) [![Image 5: semantic-release](https://camo.githubusercontent.com/251b82ec02847188c7f2f024d0a6752bb8e0422772baaace42e7a7dc3fd8c88a/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f2532302532302546302539462539332541362546302539462539412538302d73656d616e7469632d2d72656c656173652d6531303037392e737667)](https://github.com/semantic-release/semantic-release) [![Image 6: bundlephobia](https://camo.githubusercontent.com/211cb5d0cc1118de970dff1d82c933a04dc935e311b2179b4eacacc81dabeb0b/68747470733a2f2f696d672e736869656c64732e696f2f62756e646c6570686f6269612f6d696e2f657965726561736f6e65722e737667)](https://www.npmjs.com/package/eyereasoner) [![Image 7: DOI](https://camo.githubusercontent.com/8bf5d58e3b8d25b9569238c2e1a0b2ea23d9cdd508a350e692da13494d69fb99/68747470733a2f2f7a656e6f646f2e6f72672f62616467652f3538313730363535372e737667)](https://zenodo.org/doi/10.5281/zenodo.12211023)

Usage
-----

[](https://github.com/eyereasoner/eye-js/#usage)

The simplest way to use this package is to use the `n3reasoner` to execute a query over a dataset and get the results. The input `data` should include the data and any inference rules that you wish to apply to the dataset; the optional `query` should match the pattern of data you wish the engine to return; if left undefined, all new inferred facts will be returned. For example:

import { n3reasoner } from 'eyereasoner';

export const queryString \= \`
@prefix : <http://example.org/socrates#\>.
{:Socrates a ?WHAT} =\> {:Socrates a ?WHAT}.
\`;

export const dataString \= \`
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#\>.
@prefix : <http://example.org/socrates#\>.
:Socrates a :Human.
:Human rdfs:subClassOf :Mortal.
{?A rdfs:subClassOf ?B. ?S a ?A} =\> {?S a ?B}.
\`;

// The result of the query (as a string)
const resultString \= await n3reasoner(dataString, queryString);

// All inferred data
const resultString \= await n3reasoner(dataString);

_Note:_ One can also supply an array of `dataString`s rather than a single `dataString` if one has multiple input data files.

The `n3reasoner` accepts both `string`s (formatted in Notation3 syntax) and `quad`s as input. The output will be of the same type as the input `data`. This means that we can use `n3reasoner` with RDF/JS quads as follows:

import { Parser } from 'n3';

const parser \= new Parser({ format: 'text/n3' });
export const queryQuads \= parser.parse(queryString);
export const dataQuads \= parser.parse(dataString);

// The result of the query (as an array of quads)
const resultQuads \= await n3reasoner(dataQuads, queryQuads);

### Options

[](https://github.com/eyereasoner/eye-js/#options)

The `n3reasoner` function allows one to optionally pass along a set of options

import { n3reasoner } from 'eyereasoner';

const data \= \`
@prefix : <urn:example.org:\> .
:Alice a :Person .
{ ?S a :Person } =\> { ?S a :Human } .
\`;

const result \= await n3reasoner(data, undefined, {
  output: 'derivations',
  outputType: 'string'
});

The `options` parameter can be used to configure the reasoning process. The following options are available:

*   `output`: What to output with implicit queries.
    *   `derivations`: output only new derived triples, a.k.a `--pass-only-new` (default)
    *   `deductive_closure`: output deductive closure, a.k.a `--pass`
    *   `deductive_closure_plus_rules`: output deductive closure plus rules, a.k.a `--pass-all`
    *   `grounded_deductive_closure_plus_rules`: ground the rules and output deductive closure plus rules, a.k.a `--pass-all-ground`
    *   `none`: provides no `-pass-*` arguments to eye, often used when doing RDF Surface reasoning
*   `outputType`: The type of output (if different from the input)
    *   `string`: output as string
    *   `quads`: output as array of RDF/JS Quads

Advanced usage
--------------

[](https://github.com/eyereasoner/eye-js/#advanced-usage)

To have more granular control one can also use this module as follows

import { SwiplEye, queryOnce } from 'eyereasoner';

const query \= \`
@prefix : <http://example.org/socrates#\>.
{:Socrates a ?WHAT} =\> {:Socrates a ?WHAT}.
\`

const data \= \`
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#\>.
@prefix : <http://example.org/socrates#\>.
:Socrates a :Human.
:Human rdfs:subClassOf :Mortal.
{?A rdfs:subClassOf ?B. ?S a ?A} =\> {?S a ?B}.
\`

async function main() {
  // Instantiate a new SWIPL module and log any results it produces to the console
  const Module \= await SwiplEye({ print: (str: string) \=\> { console.log(str) }, arguments: \['-q'\] });

  // Load the the strings data and query as files data.n3 and query.n3 into the module
  Module.FS.writeFile('data.n3', data);
  Module.FS.writeFile('query.n3', query);

  // Execute main(\['--nope', '--quiet', './data.n3', '--query', './query.n3'\]).
  queryOnce(Module, 'main', \['--nope', '--quiet', './data.n3', '--query', './query.n3'\]);
}

main();

Selecting the `SWIPL` module
----------------------------

[](https://github.com/eyereasoner/eye-js/#selecting-the-swipl-module)

The `SWIPL` module exported from this library is a build that inlines WebAssembly and data strings in order to be isomorphic across browser and node without requiring any bundlers. Some users may wish to have more fine-grained control over their SWIPL module; for instance in order to load the `.wasm` file separately for performance. In these cases see the `SWIPL` modules exported by [npm swipl wasm](https://github.com/rla/npm-swipl-wasm/).

An example usage of the node-specific swipl-wasm build is as follows:

import { loadEyeImage, queryOnce } from 'eyereasoner';
import SWIPL from 'swipl-wasm/dist/swipl-node';

async function main() {
  const SwiplEye \= loadEyeImage(SWIPL);

  // Instantiate a new SWIPL module and log any results it produces to the console
  const Module \= await SwiplEye({ print: (str: string) \=\> { console.log(str) }, arguments: \['-q'\] });

  // Load the the strings data and query as files data.n3 and query.n3 into the module
  Module.FS.writeFile('data.n3', data);
  Module.FS.writeFile('query.n3', query);

  // Execute main(\['--nope', '--quiet', './data.n3', '--query', './query.n3'\]).
  queryOnce(Module, 'main', \['--nope', '--quiet', './data.n3', '--query', './query.n3'\]);
}

main();

CLI Usage
---------

[](https://github.com/eyereasoner/eye-js/#cli-usage)

This package also exposes a CLI interface for using the reasoner. It can be used via `npx`

# Run the command using the latest version of eyereasoner on npm
npx eyereasoner --nope --quiet ./socrates.n3 --query ./socrates-query.n3

or by globally installing `eyereasoner`

# Gloablly install eyereasoner
npm i -g eyereasoner
# Run a command with eyereasoner
eyereasoner --nope --quiet ./socrates.n3 --query ./socrates-query.n3

Browser Builds
--------------

[](https://github.com/eyereasoner/eye-js/#browser-builds)

For convenience we provide deploy bundled versions of the eyereasoner on github pages which can be directly used in an HTML document as shown in [this example](https://github.com/eyereasoner/eye-js/tree/main/examples/prebuilt/index.html) which is also [deployed on github pages](https://eyereasoner.github.io/eye-js/example/index.html).

There is a bundled version for each release - which can be found at the url:

[https://eyereasoner.github.io/eye-js/vMajor/vMinor/vPatch/index.js](https://eyereasoner.github.io/eye-js/vMajor/vMinor/vPatch/index.js)

for instance v2.3.14 has the url [https://eyereasoner.github.io/eye-js/2/3/14/index.js](https://eyereasoner.github.io/eye-js/2/3/14/index.js). We also have shortcuts for:

*   the latest version [https://eyereasoner.github.io/eye-js/latest/index.js](https://eyereasoner.github.io/eye-js/latest/index.js),
*   the latest of each major version [https://eyereasoner.github.io/eye-js/vMajor/latest/index.js](https://eyereasoner.github.io/eye-js/vMajor/latest/index.js), and
*   the latest of each minor version [https://eyereasoner.github.io/eye-js/vMajor/vMinor/latest/index.js](https://eyereasoner.github.io/eye-js/vMajor/vMinor/latest/index.js)

Available versions can be browsed at [https://github.com/eyereasoner/eye-js/tree/pages](https://github.com/eyereasoner/eye-js/tree/pages).

Github also serves these files with a `gzip` content encoding which compresses the script to ~1.4MB when being served.

[![Image 8](https://github.com/eyereasoner/eye-js/raw/main/github-transfer.png)](https://github.com/eyereasoner/eye-js/blob/main/github-transfer.png)

### Dynamic imports

[](https://github.com/eyereasoner/eye-js/#dynamic-imports)

We also distribute bundles that can be dynamically imported on github pages; for example

const { eyereasoner } \= await import('https://eyereasoner.github.io/eye-js/2/latest/dynamic-import.js');

// Instantiate a new SWIPL module and log any results it produces to the console
const Module \= await eyereasoner.SwiplEye({ print: (str) \=\> { console.log(str) }, arguments: \['-q'\] });

// Load the the strings data and query as files data.n3 and query.n3 into the module
Module.FS.writeFile('data.n3', data);
Module.FS.writeFile('query.n3', query);

// Execute main(\['--nope', '--quiet', './data.n3', '--query', './query.n3'\]).
eyereasoner.queryOnce(Module, 'main', \['--nope', '--quiet', './data.n3', '--query', './query.n3'\]);

Examples
--------

[](https://github.com/eyereasoner/eye-js/#examples)

We provide some examples of using `eyereasoner`:

*   Using as an npm package and bundling using webpack ([`./examples/rollup`](https://github.com/eyereasoner/eye-js/tree/main/examples/rollup)).
*   Using a prebuilt version of `eyereasoner` ([`./examples/prebuilt`](https://github.com/eyereasoner/eye-js/tree/main/examples/prebuilt)) - this example is [deployed on github pages](https://eyereasoner.github.io/eye-js/example/index.html).

Performance
-----------

[](https://github.com/eyereasoner/eye-js/#performance)

We use [benchmark.js](https://benchmarkjs.com/) to collect the performance results of some basic operations. Those results are published [here](https://eyereasoner.github.io/eye-js/dev/bench/).

Experimental `linguareasoner`
-----------------------------

[](https://github.com/eyereasoner/eye-js/#experimental-linguareasoner)

We have experimental support for RDF Lingua using the `linguareasoner`; similarly to `n3reasoner` it can be used with both string and quad input/output. For instance:

import { linguareasoner } from 'eyereasoner';

const result \= await linguareasoner(\`
\# ------------------
\# Socrates Inference
\# ------------------
#
\# Infer that Socrates is mortal.
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\>.
@prefix var: <http://www.w3.org/2000/10/swap/var#\>.
@prefix : <http://example.org/socrates#\>.
\# facts
:Socrates a :Human.
:Human rdfs:subClassOf :Mortal.
\# rdfs subclass
\_:ng1 log:implies \_:ng2.
\_:ng1 {
    var:A rdfs:subClassOf var:B.
    var:S a var:A.
}
\_:ng2 {
    var:S a var:B.
}
\# query
\_:ng3 log:query \_:ng3.
\_:ng3 {
    var:S a :Mortal.
}\`)

Cite
----

[](https://github.com/eyereasoner/eye-js/#cite)

If you are using or extending eye-js as part of a scientific publication, we would appreciate a citation of our [zenodo artefact](https://zenodo.org/doi/10.5281/zenodo.12211023).

License
-------

[](https://github.com/eyereasoner/eye-js/#license)

©2022–present [Jesse Wright](https://github.com/jeswr), [Jos De Roo](https://github.com/josd/), [MIT License](https://github.com/eyereasoner/eye-js/blob/master/LICENSE).