When we say [[User]] we simply mean an [[Agent]] who is using the system in some way; the concept of a user is not a technical term that refers to any particular resource or account.

Often, a user will be someone who has opened a link in their web browser, perhaps some resource on the [[Node.Town]] web server. They can browse around, fill in forms, do various things that the [[Hypermedia]] controls present as [[Affordance]]s. They might not have gone through any kind of [[Authentication]] and may not be linked to any [[Identity]].

We want to avoid building the system around a typical user account regime where the first step is always to log in to an authenticated [[Web Session]] and where the same [[URL]] yields entirely different contents depending on identity. As [[Roy Fielding]] has stated, such schemes are inappropriate for web resources since they undermine the [[REST]] model of application state.

![[Architectural Styles and the Design of Network-based Software Architectures#^cookies-bad]]

It's often convenient for a person to use a system through a [[User Account]] because it acts as a [[Resource Scope]], an identifier for [[Attribution]], and a subject for [[Access Control]]. But all of this can be seen instead from the perspective of [[Object Capabilities]] represented as [[Web Resources]], [[Hypermedia]], and [[Linked Data]].
## Object Capabilities as Hypermedia Resources

If you know a URL, you can make a request for the resource the URL denotes, so a [[Secret URL]] is a good way to represent a read capability. If the representation you get contains a [[Hypermedia Control]] like a [[Form]], the URL also gives its bearer whatever capability that control denotes.

> [!example]
> A "user account" in a social media platform can be just a secret URL that resolves to a page with a link to a timeline and a form for posting a note. The link would be another secret URL and the form would post to yet another. You can give another user read-only access to the timeline by sending them the link, or grant posting access without exposing the timeline by sharing only the form.

It is then inherently possible to run a [[Web Proxy]] that does any kind of [[Delegation]] or [[Attenuation]] imaginable, so we easily obtain a rich system of [[Object Capabilities]] without even the notion of an authenticated user account.

The fact that a web server has internal logic is what allows representing capabilities as URLs. There is no general way to discover what a web server will respond to a request. A proxy, for example, can forward requests to another server without revealing the address of that server, which enables delegation, or attach an identifier to its outgoing requests without revealing it to the proxy's user.

This should be the basic principle of [[Node.Town]] access control even when instead of web proxies we use some internal server logic. The program starts with a core set of root capabilities which give rise to networks of derived capabilities through attenuation and combination.

A [[Capability]] typically has a URL that resolves to a document containing links and forms. These documents can be represented as [[Hypertext Markup]] or as [[Linked Data]] in any [[RDF]] format.

> [!example]
> A capability to generate images with a certain image model can be a link to a HTML page with a form that has a prompt field, an aspect ratio selector, and various other parameters. The form's target is an unguessable URL. The server responds to post requests by invoking an API with some access token—causing the inference provider to debit a certain account for the inference fee—and forwarding the generated image response.

If my capability bundle is just a web resource, the only login method I need is a bookmark or a saved link in my notes. Keeping it secret is just like keeping any secret and sharing it is even easier.

See [[Authentication as an Event]].