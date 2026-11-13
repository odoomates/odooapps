import { after } from "@odoo/hoot";

/**
 * Answer the requests of the page as the extension would; ``answer`` gets the
 * request and returns (or resolves to) the fields of the answer. Returns the
 * list of the requests received.
 */
export function fakeExtension(answer) {
    const requests = [];
    const onMessage = async (event) => {
        if (typeof event.data !== "string") {
            return;
        }
        const request = JSON.parse(event.data);
        if (request.source !== "om-whatsapp-web") {
            return;
        }
        requests.push(request);
        const fields = await answer(request);
        window.postMessage(
            JSON.stringify({ source: "om-whatsapp-extension", id: request.id, ...fields }),
            window.location.origin
        );
    };
    window.addEventListener("message", onMessage);
    after(() => window.removeEventListener("message", onMessage));
    return requests;
}
