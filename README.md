# slack-export-filter: A tool for searching your Slack history

If you've exported past messages from a Slack workspace, you know that you then face the daunting prospect of trying to find anything in it. grep works on the export's JSON files, but it doesn't understand structures and so can only do the most rudimentary text-searching, without consideration of message dates or authors.

What you might yearn for is a tool that understands (at least some approximation of some subset of) Slack's own search syntax, including its special prefix keywords, and is able to efficiently search the messages using a Slack-compatible query—including by content, date, author, or all three.

That's what this tool does.

## Usage
```
slack-export-filter <query> <path-to-export>
```

The exported history must reside entirely within a directory; this tool does not support archive files.

Queries use Slack's own search syntax. Support for it is not complete and probably has some differences; please file bugs for anything that's missing or doesn't work correctly.

Currently supported:

- `in:<channel>`
- `from:<user>` (by username or user ID)
- `is:thread`
- `on:<date>`
- `during:<month>`
- `before:<date>` (or `until:`, after Twitter's search syntax)
- `after:<date>` (or `since:`)
- words, regardless of order
- quoted phrases

Matching messages are printed in a format resembling an IRC chat log, separated with dashed lines since messages may be multiple lines.
