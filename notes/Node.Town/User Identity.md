A [[Bubble]] is not necessarily specific to a single person or agent; it may be used by several.

There should be a [[Root Identity]] for each bubble. It would correspond to the [[Keypair]] that's generated when creating a [[Repository]].

It should be possible to create a new [[User]] using the root identity.

Creating a new user should be a [[Capability]]. That means there should be an [[Actor]] corresponding to the [[Root Identity]] which responds to user creation messages.

So we should spawn a [[Root Actor]].

This brings up the question of [[Actor Identity]].

See [[The Concept of a User]].