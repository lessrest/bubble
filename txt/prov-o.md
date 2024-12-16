# PROV Ontology (PROV-O) Reference

A concise summary of the PROV Ontology (PROV-O) classes and properties. This
summary provides precise, informative definitions and brief examples for each
class and property, offering insight into how they are used to model
provenance information.

## Core Classes

### prov:Entity

A physical, digital, conceptual, or other kind of thing with some fixed
aspects. Entities may be real or imaginary.

**Example:** A dataset, a document, an image.

**Key Properties:**

- `prov:wasGeneratedBy`: Links an entity to the activity that generated it.
- `prov:wasDerivedFrom`: Links an entity to another entity from which it was
  derived.

### prov:Activity

Something that occurs over a period of time and acts upon or with entities,
possibly generating new entities.

**Example:** A data cleaning process, a painting session, a file conversion.

**Key Properties:**

- `prov:used`: Indicates the entity an activity used.
- `prov:wasInformedBy`: Indicates an activity was informed by another
  activity.
- `prov:startedAtTime` / `prov:endedAtTime`: Marks when an activity
  began/ended.

### prov:Agent

Something that bears responsibility for an activity, existence of an entity,
or another agent's activity.

**Example:** A person, an organization, a software agent (like a script or
bot).

**Key Properties:**

- `prov:wasAssociatedWith`: Associates an activity with an agent.
- `prov:wasAttributedTo`: Attributes an entity's existence to an agent.
- `prov:actedOnBehalfOf`: Indicates one agent acted under the authority of
  another.

## Expanded Classes

### prov:Collection

An entity that provides a structure (e.g., set, list) to its members
(entities).

**Example:** A dataset containing multiple files.

**Key Property:**

- `prov:hadMember`: Lists the entities that are members of the collection.

### prov:EmptyCollection

A collection with no members.

### prov:Bundle

A named set of provenance descriptions, which itself can have provenance.

**Example:** A file containing RDF triples describing provenance.

### prov:Person

A person.

**Example:** "Alice," a human user.

### prov:Organization

A social or legal institution.

**Example:** "ACME Inc."

### prov:SoftwareAgent

Running software that acts as an agent.

**Example:** A web crawler (e.g., "Googlebot").

### prov:Location

A place, either physical (e.g., coordinates) or abstract (e.g., a directory).

**Key Property:**

- `prov:atLocation`: Indicates a location associated with entities,
  activities, or events.

## Expanded Properties

- `prov:alternateOf`: Relates two entities that represent the same thing,
  possibly from different viewpoints or times.
- `prov:specializationOf`: Links an entity to a more general entity of which
  it is a specialization.
- `prov:generatedAtTime`: The time at which an entity was fully created.
- `prov:value`: A direct representation of an entity's value (e.g., a literal
  text or number).
- `prov:hadPrimarySource`: Indicates an entity's derivation from an earlier,
  primary entity.
- `prov:wasQuotedFrom`: Indicates an entity is directly quoted from another.
- `prov:wasRevisionOf`: Indicates an entity is a revised version of another.
- `prov:invalidatedAtTime`: The time when an entity became invalid or ceased
  to exist.
- `prov:wasInvalidatedBy`: Links an entity to the activity that invalidated
  it.
- `prov:wasStartedBy`: Indicates that an entity triggered the start of an
  activity.
- `prov:wasEndedBy`: Indicates that an entity triggered the end of an
  activity.
- `prov:invalidated`: The inverse perspective (from the activity's side) of
  invalidation.
- `prov:influenced`: A broad superproperty indicating any influence from one
  thing to another.
- `prov:generated`: Inverse perspective of generation (activity generated
  entity).

## Qualified Classes for Influences

These classes enable qualification of the simple relations above, adding
detail such as time, role, or additional agents or plans involved.

### prov:Influence

The capacity of one entity/activity/agent to affect another.

**Subclasses:**

- prov:EntityInfluence: Influence of an entity.
- prov:ActivityInfluence: Influence of an activity.
- prov:AgentInfluence: Influence of an agent.

### prov:Usage

Qualifies how an activity used an entity (e.g., at a specific time, in a
specific role).

**Properties:**

- `prov:entity`: The used entity.
- `prov:atTime`: When it was used.
- `prov:hadRole`: The function of the entity in this usage.

### prov:Generation

Qualifies how an activity generated an entity.

**Properties:**

- `prov:activity`: The activity that generated.
- `prov:atTime`: The generation time.

### prov:Invalidation

Qualifies how an activity invalidated (ended) an entity's existence.

**Properties:**

- `prov:activity`: The invalidating activity.
- `prov:atTime`: When it was invalidated.

### prov:Communication

Qualifies how one activity informed another.

**Property:**

- `prov:activity`: The informing activity.

### prov:Derivation

Qualifies how one entity was derived from another (e.g., citing the activity,
usage, and generation involved).

**Properties:**

- `prov:entity`: The source entity.
- `prov:hadActivity`: The activity that contributed to the derivation.

**Specialized forms of Derivation:**

- prov:PrimarySource: Qualifies a primary source relationship.
- prov:Quotation: Qualifies a quotation relationship.
- prov:Revision: Qualifies a revision relationship.

### prov:Association

Qualifies how an agent was associated with an activity (responsibility, roles,
and possible plans).

**Properties:**

- `prov:agent`: The responsible agent.
- `prov:hadRole`: The role the agent played.
- `prov:hadPlan`: A plan guiding the activity.

### prov:Attribution

Qualifies how an agent is responsible for an entity's existence.

**Property:**

- `prov:agent`: The attributing agent.

### prov:Delegation

Qualifies how one agent acted on behalf of another.

**Properties:**

- `prov:agent`: The superior agent granting authority.
- `prov:hadActivity`: An activity possibly related to that delegation.

### prov:Start & prov:End

Qualify the exact moment (and possibly the trigger entity) that caused an
activity to start or end.

**Properties:**

- `prov:entity`: The entity that initiated ending or starting.
- `prov:atTime`: The time of starting or ending.

### prov:Plan

An entity that embodies a set of intended actions or steps by an agent.

**Used With:** prov:hadPlan in an Association.

### prov:Role

The function played by an entity or agent in the context of an activity or
influence.

**Example:** "Input dataset," "Lead researcher," "Instrument."

## Qualified Properties

- `prov:qualifiedInfluence`: Points to an Influence class instance to detail
  how something influenced something else.
- Specific qualified properties:
  - `qualifiedGeneration`
  - `qualifiedDerivation`
  - `qualifiedAttribution`
  - `qualifiedUsage`
  - `qualifiedCommunication`
  - `qualifiedAssociation`
  - `qualifiedStart`
  - `qualifiedEnd`
  - `qualifiedInvalidation`
  - `qualifiedQuotation`
  - `qualifiedPrimarySource`
  - `qualifiedRevision`
  - `qualifiedDelegation`

### Example:

:chart prov:wasGeneratedBy :activity; prov:qualifiedGeneration [ a
prov:Generation; prov:activity :activity; prov:atTime
"2021-01-01T10:00:00Z"^^xsd:dateTime; ].

This provides richer detail about how and when :chart was generated by
:activity.

## Other Supporting Properties

- `prov:atTime`: Specifies the exact time at which an event (usage,
  generation, invalidation, start, end) occurred.
- `prov:hadRole`: Describes the role an entity or agent played in the
  influence.
- `prov:hadActivity`: Links an influence to an activity that played a part in
  the influence.

By combining these classes and properties, PROV-O allows you to represent and
interlink detailed provenance graphs, capturing the who, what, when, where,
why, and how of data production, transformation, and usage.
