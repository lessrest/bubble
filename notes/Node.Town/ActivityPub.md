# Integration

ActivityPub is a decentralized social networking protocol that enables
different systems to communicate and share activities in a standardized way.
It's particularly relevant for Bubble because:

1. It aligns with our distributed "froth" architecture where bubbles need to
   interact
2. It provides a standard way to handle actor identities and capabilities
3. It fits naturally with our existing RDF/semantic foundation

## Implementation Strategy

First of all, we need some notion of [[User Identity]] and [[Authentication]].

1. **Identity Layer**

   - Extend existing DID implementation
   - Map bubble identities to ActivityPub actors
   - Use existing key infrastructure for signing

2. **Protocol Support**

   - Implement basic ActivityPub endpoints (inbox/outbox)
   - Build on existing WebSocket infrastructure
   - Leverage N3 rules for activity processing

3. **Storage and Distribution**
   - Store activities in git repository
   - Use existing froth networking for federation
   - Maintain provenance using PROV ontology

## Next Steps

- [ ] Define ActivityPub actor profile format
- [ ] Implement basic inbox/outbox endpoints
- [ ] Add ActivityPub vocabulary to our RDF schemas
- [ ] Extend peer networking for ActivityPub federation
- [ ] Create N3 rules for common ActivityPub activities

# [[ActivityStreams]] Ontology

ActivityStreams 2.0 defines a structured, RDF-compatible JSON-LD vocabulary
for describing social activities, actors, and objects. Core classes and
properties include:

## Classes

### `as:Object`

Base class for all entities in the system

- Properties: `as:id`, `as:type`, `as:name`, `as:content`, `as:published`,
  `as:updated`, `as:attributedTo`

- **`as:Note`** — text-based content

  - Key properties: `as:content`, `as:contentMap`, `as:summary`
  - Often used for status updates, comments, and replies

- **`as:Image`** — visual media

  - Key properties: `as:url`, `as:mediaType`, `as:width`, `as:height`,
    `as:preview`
  - Can include multiple resolution variants via url arrays

- **`as:Article`** — long-form content

  - Key properties: `as:content`, `as:summary`, `as:name`, `as:attachment`
  - Often includes html content and multiple media attachments

- **`as:Document`** — generic document type

  - Key properties: `as:url`, `as:mediaType`, `as:name`, `as:duration`
  - Used for files, attachments, and other binary content

- **`as:Event`** — time-based occurrence

  - Key properties: `as:startTime`, `as:endTime`, `as:location`, `as:attendee`
  - Can reference Place objects and track participation

- **`as:Place`** — location or venue

  - Key properties: `as:latitude`, `as:longitude`, `as:altitude`, `as:radius`,
    `as:accuracy`
  - Used for geo-tagging and location-based activities

- **`as:Activity`** — action performed by an actor

  - Common properties: `as:actor`, `as:object`, `as:target`, `as:result`,
    `as:origin`
  - **`as:Create`** — making new content
    - Requires `as:object` property specifying the created item
  - **`as:Like`** — expressing approval
    - `as:object` property references the liked content
  - **`as:Follow`** — subscribing to updates
    - `as:object` property references the followed actor
  - **`as:Delete`** — removing content
    - `as:object` property references content to remove
  - **`as:Update`** — modifying content
    - `as:object` property contains new version
  - **`as:Add`** — including in a collection
    - Requires `as:target` (collection) and `as:object` (item to add)
  - **`as:Remove`** — excluding from a collection
    - Requires `as:target` (collection) and `as:object` (item to remove)

- **`as:Actor`** — entity capable of performing activities

  - Common properties: `as:inbox`, `as:outbox`, `as:following`,
    `as:followers`, `as:liked`
  - **`as:Person`** — individual user
    - Properties: `as:preferredUsername`, `as:publicKey`, `as:endpoints`
  - **`as:Service`** — automated system
    - Properties: `as:endpoints`, `as:publicKey`
  - **`as:Group`** — collection of actors
    - Properties: `as:members`, `as:memberOf`
  - **`as:Organization`** — formal group
    - Properties: `as:members`, `as:memberOf`
  - **`as:Application`** — software agent
    - Properties: `as:endpoints`, `as:publicKey`

- **`as:Collection`** — container for multiple objects

  - Properties: `as:totalItems`, `as:current`, `as:first`, `as:last`,
    `as:items`
  - **`as:OrderedCollection`** — sequence-preserving container
    - Adds `as:orderedItems` property with array semantics

- **`as:CollectionPage`** — paginated subset of a collection
  - Properties: `as:partOf`, `as:next`, `as:prev`
  - **`as:OrderedCollectionPage`** — paginated subset of an ordered collection
    - Maintains order with `as:startIndex` property

## Key Properties and Relations

### Core Object Properties

| Property          | Domain                 | Range                          | Description                                                          |
| ----------------- | ---------------------- | ------------------------------ | -------------------------------------------------------------------- |
| `as:id`           | `as:Object`, `as:Link` | `xsd:anyURI`                   | A globally unique IRI identifier for the object                      |
| `as:type`         | `as:Object`, `as:Link` | `xsd:anyURI`                   | The type of the object (e.g., `as:Note`, `as:Person`, `as:Activity`) |
| `as:name`         | `as:Object`, `as:Link` | `rdf:langString`, `xsd:string` | The plain-text display name of the object                            |
| `as:content`      | `as:Object`            | `rdf:langString`, `xsd:string` | The primary content of the object (supports HTML or plain text)      |
| `as:published`    | `as:Object`            | `xsd:dateTime`                 | Timestamp when the object was published                              |
| `as:updated`      | `as:Object`            | `xsd:dateTime`                 | Timestamp when the object was last modified                          |
| `as:attributedTo` | `as:Object`, `as:Link` | `as:Object`, `as:Link`         | Links to the actor(s) who created the object                         |

### Activity-Specific Properties

| Property        | Domain                           | Range                  | Description                                                |
| --------------- | -------------------------------- | ---------------------- | ---------------------------------------------------------- |
| `as:actor`      | `as:Activity`                    | `as:Object`, `as:Link` | The entity performing the activity (must be an Actor type) |
| `as:object`     | `as:Activity`, `as:Relationship` | `as:Object`, `as:Link` | The primary object the activity acts upon                  |
| `as:target`     | `as:Activity`                    | `as:Object`, `as:Link` | An optional indirect object or target of the activity      |
| `as:result`     | `as:Activity`                    | `as:Object`, `as:Link` | The result of performing the activity                      |
| `as:origin`     | `as:Activity`                    | `as:Object`, `as:Link` | Where the activity was initiated from                      |
| `as:instrument` | `as:Activity`                    | `as:Object`, `as:Link` | Tools/methods used to perform the activity                 |

### Relationship Properties

| Property          | Domain            | Range                  | Description                                                                             |
| ----------------- | ----------------- | ---------------------- | --------------------------------------------------------------------------------------- |
| `as:subject`      | `as:Relationship` | `as:Object`, `as:Link` | In a Relationship object, identifies the subject (e.g., "John" in "John follows Sally") |
| `as:relationship` | `as:Relationship` | `rdf:Property`         | Describes the type of relationship between actors                                       |
| `as:following`    | `as:Actor`        | `as:Collection`        | Collection of actors that this actor follows                                            |
| `as:followers`    | `as:Actor`        | `as:Collection`        | Collection of actors that follow this actor                                             |
| `as:liked`        | `as:Actor`        | `as:Collection`        | Collection of objects this actor has liked                                              |

### Collection Properties

| Property          | Domain                 | Range                                     | Description                                  |
| ----------------- | ---------------------- | ----------------------------------------- | -------------------------------------------- |
| `as:items`        | `as:Collection`        | `as:Object`, `as:Link`, `as:OrderedItems` | The items in a collection (unordered)        |
| `as:orderedItems` | `as:OrderedCollection` | `as:OrderedItems`                         | The items in a collection (strictly ordered) |
| `as:totalItems`   | `as:Collection`        | `xsd:nonNegativeInteger`                  | The total number of items in the collection  |
| `as:current`      | `as:Collection`        | `as:CollectionPage`, `as:Link`            | The current page of a collection             |
| `as:first`        | `as:Collection`        | `as:CollectionPage`, `as:Link`            | The first page of a collection               |
| `as:last`         | `as:Collection`        | `as:CollectionPage`, `as:Link`            | The last page of a collection                |
| `as:next`         | `as:CollectionPage`    | `as:CollectionPage`, `as:Link`            | The next page in a collection                |
| `as:prev`         | `as:CollectionPage`    | `as:CollectionPage`, `as:Link`            | The previous page in a collection            |

### Addressing Properties

| Property      | Domain      | Range                  | Description                          |
| ------------- | ----------- | ---------------------- | ------------------------------------ |
| `as:to`       | `as:Object` | `as:Object`, `as:Link` | Primary recipients of the object     |
| `as:cc`       | `as:Object` | `as:Object`, `as:Link` | Secondary recipients ("carbon copy") |
| `as:bto`      | `as:Object` | `as:Object`, `as:Link` | Primary recipients (private)         |
| `as:bcc`      | `as:Object` | `as:Object`, `as:Link` | Secondary recipients (private)       |
| `as:audience` | `as:Object` | `as:Object`, `as:Link` | Intended audience for the object     |

### Media Properties

| Property       | Domain                 | Range                    | Description                          |
| -------------- | ---------------------- | ------------------------ | ------------------------------------ |
| `as:url`       | `as:Object`            | `as:Link`, `xsd:anyURI`  | URL where the object can be accessed |
| `as:mediaType` | `as:Object`, `as:Link` | `xsd:string`             | MIME type of the object              |
| `as:duration`  | `as:Object`            | `xsd:duration`           | Duration of media content            |
| `as:height`    | `as:Link`              | `xsd:nonNegativeInteger` | Height of visual content in pixels   |
| `as:width`     | `as:Link`              | `xsd:nonNegativeInteger` | Width of visual content in pixels    |
| `as:preview`   | `as:Object`, `as:Link` | `as:Object`, `as:Link`   | Preview or thumbnail of the object   |

### Location Properties

| Property       | Domain      | Range                                                     | Description                          |
| -------------- | ----------- | --------------------------------------------------------- | ------------------------------------ |
| `as:location`  | `as:Object` | `as:Object`, `as:Link`                                    | Physical or logical location         |
| `as:latitude`  | `as:Place`  | `xsd:float`                                               | Latitude coordinate                  |
| `as:longitude` | `as:Place`  | `xsd:float`                                               | Longitude coordinate                 |
| `as:altitude`  | `as:Place`  | `xsd:float`                                               | Altitude in meters                   |
| `as:accuracy`  | `as:Place`  | `xsd:float [>= 0.0]`                                      | Accuracy of coordinates in meters    |
| `as:radius`    | `as:Place`  | `xsd:float [>= 0.0]`                                      | Radius around coordinates in meters  |
| `as:units`     | `as:Place`  | `{"cm","feet","inches","km","m","miles"}` or `xsd:anyURI` | Units used for location measurements |

# ActivityPub Architectural Principles

ActivityPub builds upon the ActivityStreams vocabulary to specify
interoperability protocols. It defines a set of client-to-server (C2S) and
server-to-server (S2S) interactions that leverage the aforementioned classes
and relations:

## Actors as Addressable Resources

Each `as:Actor` is a public, dereferenceable resource (e.g., via
https://example.com/user/alice). The actor's id IRI identifies it globally
within the federation.

## Federated Delivery of Activities

ActivityPub specifies that servers deliver `as:Activity` objects to
recipients' `as:inbox` collections. These deliveries rely on the standardized
use of `as:inbox`, `as:outbox`, and `as:followers` relations to route
activities between federated domains.

## Client-to-Server Interactions

Clients create, update, and delete content (instances of `as:Object` and
`as:Activity`) via authenticated operations against the actor's `as:outbox`
and related endpoints. The server responds with ActivityStreams
representations of created or modified resources, ensuring consistent RDF
graph data.

## Server-to-Server Interactions (Federation)

Remote servers retrieve actor objects, follow relationships, and send
`as:Activity` objects to an actor's `as:inbox`. The receiving server processes
incoming activities (e.g., adding `as:Follow` relationships, distributing
`as:Create` posts to local followers, or incrementing `as:Like` counts),
maintaining a shared, decentralized social graph across multiple trusted and
semi-trusted domains.

## JSON-LD and Extensibility

Both ActivityStreams and ActivityPub rely on JSON-LD for RDF compatibility. By
defining or referencing JSON-LD contexts, implementers can introduce
additional classes and properties while preserving semantic interoperability.
Extensions must remain compatible with the core vocabulary so all
participating implementations can reliably process extended data.

## Related

- [[User Identity]]
- [[Actor Identity]]
