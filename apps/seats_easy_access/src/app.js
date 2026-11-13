'use strict';
require('./ui').run().catch((e) => {
    console.error('Seats Easy Access startup failed: ' + (e.stack || e));
    // Stay idle for the platform to stop the app instead of repeatedly crashing it.
    setInterval(function () {}, 30000);
});
