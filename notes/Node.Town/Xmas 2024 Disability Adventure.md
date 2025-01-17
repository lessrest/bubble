I broke my arm the other day, and it's actually turned into something of a blessing in disguise. It's given me real motivation to build something I genuinely need: a system that lets me chat with my brother through voice while incorporating AI tools. The injury has made me realize just how important [[Accessibility]] is in the software we use daily.

I've started by setting up an instance on [[Fly.io]], though it's not quite where I need it to be yet. I want to get [[ActivityPub]] working in real-time with speech recognition and software agents. So far, I've set up the [[swa.sh]] domain as an alias to the Fly.io instance. I'll admit I'm a bit hesitant about running the [[Speech Recognition]] component—there's this nagging worry that it might overwhelm my database. I'm not entirely sure about all its implications yet.

What I'm envisioning for the interface is something really straightforward. When you first arrive, you'd see an option to create a new chat. Clicking that would take you to an empty graph where you could start fresh. You'd be able to create identities for participants—one for yourself, one for whoever you're chatting with—and the system would generate invitation links for them. When they join, you'd both be able to use voice input, and see your words appear in real-time on a shared timeline.

On the technical side, I want to handle configuration in a smarter way. Instead of relying on environment variables, I'm planning to store API keys and other [[Secret Token]]s in the graph database, taking advantage of the persistent volume I've set up on Fly.io. This feels like a more elegant solution.

The clustering aspect is particularly interesting. I need to handle multiple instances running simultaneously, both for rolling deployments and redundancy. Right now, I have multiple machines running on Fly.io, and when you refresh the website, you randomly get different node IDs. I've learned about implementing clustering through DNS lookups—basically checking an internal DNS name like `appname.internal` every five seconds to get a list of all machines. I have some code for connecting nodes to each other, but I still need to implement cross-server communication and integration. This might involve [[Graph Replication]], though I need to think that through more carefully.

I've been getting much better at using dictation and voice control in macOS. It's quite liberating—right now I'm standing up while dictating this, switching between applications with voice commands. I'm still learning all the commands, but it's already proving incredibly useful.

This experience has really opened my eyes to accessibility issues in popular apps. [[Telegram]], for instance, doesn't properly expose widget names, making it frustrating to use with assistive technologies. Twitter's website is similarly problematic, with a confusing widget structure that makes navigation difficult. These observations have made it clear that *swa.sh* needs to be accessible from the ground up, supporting voice control, screen readers, and other accessibility paradigms. My current situation with my arm has turned into a powerful motivator to get this right.

When it comes to implementing the actor mesh cluster, there are some interesting challenges to work through. When you have multiple instances sharing the same base URL but different keypairs due to different repositories, you want them to work together seamlessly. Any URL should return consistent resources regardless of which instance handles the request. I'm thinking about implementing a special connection mode where servers can fuse together, keeping their data synchronized through repository replication and live updates.

The actor management system raises some interesting questions too. Currently, when we start the server, it launches several actors with specific capabilities. We need to carefully consider whether to duplicate these across all instances or have certain specialized nodes. While redundancy is important - if one server goes down, you want others to pick up the slack - there might be cases where you want certain services to run on specific nodes only.

For the clustering implementation, I'm considering using a [[Message Bus]] approach, possibly MQTT or NATS. Since we're working within a trusted cluster on an internal network, we can be a bit more relaxed about security (no need for certificates and TLS). One machine could run as a hub, or perhaps one per region, which might be simpler than managing peer-to-peer connections. This needs to tie into our handling of names, permanence, and [[Actor Identity]], possibly through a multiplexed actor system.

## ugh field report

I wonder what it is about the system that makes me so reluctant to do real time stuff you know with Web sockets and live updating HTML stuff it just feels like somehow horrible and I'm not exactly sure why.

Some of it is just injury that it's hard to do anything so I'm reluctant to get into the weeds maybe I should have a little nap.

## simple chat session

So I started implementing some kind of simple chat session avoidance thingy and I'm wondering how to do it like OK I click chat and I get a thing with a text box but now I want to invite somebody like I wanna invite my brother to chat with me that means I want to be able to maybe like type his name into a form and then click create participant or invite participant or maybe there should not be ascend prompt and the chat itself that should be something you get when you join and you join as a user name you join as