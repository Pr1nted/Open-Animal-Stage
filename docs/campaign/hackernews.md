# Hacker News

A draft; nothing has been posted. Submit the itch page's URL (not a blog post
about it), then add the first comment straight away, from the same account.

HN's register: plain, specific, no adjectives about your own work, no emoji, no
"excited to share". A Show HN must be something people can try, which this is:
it runs in the browser with no sign-up. Do not ask anyone to upvote it, anywhere.

## Title

> Show HN: Open Animal Stage – mapped animal brains play a strategy game together

(79 characters; HN's limit is 80.)

## URL

`<URL>` (the itch page)

## First comment

> This is a sister project to Open Fly, which put one simulated fruit-fly brain (FlyWire, 138,639 neurons, the Shiu et al. 2024 leaky integrate-and-fire model) in front of Open Doctrines, a browser grand strategy game I also make. This one puts several brains in the same world: both sexes of adult fly (FlyWire and MaleCNS v1.0), a zebrafish larva (Fish1), a sea squirt larva, and in a local copy the two C. elegans sexes and the fly larva, whose data has no licence that allows me to serve it.
>
> Each turn, the country's situation becomes four numbers (reward, harm, reserve, threat). Those drive sensory neurons named from each dataset's own annotations. The brain runs for 200 ms of simulated time, and its motor neurons are dealt into the game's 39 action groups. Every animal gets the same neuron model and the same encode and decode, written down before it played.
>
> Things I would rather say up front than have pointed out:
>
> - Putting two animals on the stage compares two mappings I wrote, not two animals. The page never ranks species.
> - The meaningful control is an animal against its own wiring, shuffled and matched for activity. With its real wiring the fly is more active and more aggressive than with shuffled wiring, and against the game's AI that loses land. That is all I am claiming.
> - Several datasets are incomplete. Fish1's axons are mostly not yet connected to their cell bodies, so the fish senses through four brain nuclei by a convention I chose. Only 243 of the fly larva's 2,952 neurons have a published transmitter. The page shows these as warnings beside the animal.
> - The mouse does not play. MICrONS is visual cortex with no motor output, so instead the map is shown to the MICrONS digital twin (Wang et al., Nature 2025), exported to ONNX and run with onnxruntime-web, and the page draws its predicted response for 8,221 recorded neurons.
> - Nothing here learned, and nothing here can feel anything. These are simplified models.
>
> Technically it is a static page: Open Doctrines compiled to WebAssembly, one Web Worker per brain, and the twin on WebGPU where it is available. Credits and licences for every dataset are on the page. I'm happy to go into any of it.
