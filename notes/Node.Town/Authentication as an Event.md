Authenticating is an event that relates an actor to an identity claim via some kind of proof process.

For example, [[Login with Telegram]] lets you authenticate as someone who controls a certain Telegram account. The identity claim denoted by a [[Public Key]] can be cryptographically authenticated by using the [[Private Key]] to sign a challenge.

It's useful to be able to authenticate with Google, GitHub, or Telegram, because those services are widely recognized, have significant trust as identity providers, and offer convenient, standardized methods of authentication.

I might not want to possess unrevokable URL capabilities for sensitive resources, and choose to condition my capabilities on third-party authentication. That means I want the server to respond to authentication events with temporary capabilities, perhaps with more than one identity provider for redundancy.

We can view that as defining how to interpret a certain kind of authentication event. It seems appropriate to do this in terms of logical rules.