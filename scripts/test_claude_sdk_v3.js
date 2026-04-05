const sdk = require('@anthropic-ai/claude-agent-sdk');

async function test() {
    try {
        console.log('Starting SDK...');
        const api = await sdk.startup();

        console.log('Sending query...');
        const session = await api.query('What is 2+2? Reply with just the number.');

        console.log('Session initialized. Iterating messages...');

        // sdkMessages is an AsyncGenerator
        const messages = session.sdkMessages;
        if (messages && typeof messages[Symbol.asyncIterator] === 'function') {
            console.log('Found async iterator, iterating...');

            let count = 0;
            const maxMessages = 10;  // Prevent infinite loop

            for await (const msg of messages) {
                count++;
                console.log(`\n--- Message ${count} ---`);
                console.log('Type:', msg.type || 'unknown');
                console.log('Content:', JSON.stringify(msg.content || msg, null, 2).slice(0, 500));

                // Stop after getting actual content or reaching limit
                if (msg.type === 'result' || count >= maxMessages) {
                    console.log('\nBreaking loop...');
                    break;
                }
            }

            console.log(`\nTotal messages processed: ${count}`);
        } else {
            console.log('No async iterator found on sdkMessages');
        }

        await api.close();
        console.log('\nDone');
    } catch (e) {
        console.error('Error:', e.message);
        console.error('Stack:', e.stack);
    }
}

test();