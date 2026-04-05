const sdk = require('@anthropic-ai/claude-agent-sdk');

async function test() {
    try {
        console.log('Starting SDK...');
        const api = await sdk.startup();

        console.log('Sending query...');
        const session = await api.query('What is 2+2? Reply with just the number.');

        console.log('Session ID or info:', session);

        // Try to get messages
        if (session && session.transport) {
            console.log('\nWaiting for response...');
            await new Promise(resolve => setTimeout(resolve, 5000));
        }

        // Try getSessionMessages
        try {
            const messages = sdk.getSessionMessages(session);
            console.log('Session messages:', JSON.stringify(messages, null, 2));
        } catch (e) {
            console.log('getSessionMessages failed:', e.message);
        }

        // Try getSessionInfo
        try {
            const info = sdk.getSessionInfo(session);
            console.log('Session info:', JSON.stringify(info, null, 2));
        } catch (e) {
            console.log('getSessionInfo failed:', e.message);
        }

        await api.close();
        console.log('\nDone');
    } catch (e) {
        console.error('Error:', e.message);
        console.error('Stack:', e.stack);
    }
}

test();