// One shell for every student rather than a path per student: the site is
// prerendered and the usernames are not known at build time. The username
// travels in the query string, as /spots/listing carries an owner listing.
export const prerender = true;
