# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: pipeline.spec.ts >> Deals CRUD >> deals - create
- Location: e2e/pipeline.spec.ts:243:3

# Error details

```
Error: apiRequestContext.post: connect ECONNREFUSED ::1:8088
Call log:
  - → POST http://localhost:8088/contacts
    - user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.7827.55 Safari/537.36
    - accept: */*
    - accept-encoding: gzip,deflate,br
    - Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidHlwZSI6ImFjY2VzcyIsImp0aSI6ImZkNjRjNTc5LTE1OWUtNDYyNy05Y2Q1LWUzYTZjNmFiZGYzNSIsImlhdCI6MTc4MzA4NTcwMSwiZXhwIjoxNzgzMDg3NTAxfQ.qW-4jgT5BOgjmQa__n58aUvtXgib4SUURQDqasmTJZo
    - content-type: application/json
    - content-length: 32

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]:
        - img [ref=e8]
        - generic [ref=e13]: CloseLoop CRM
      - navigation [ref=e14]:
        - button "Pipeline" [ref=e15] [cursor=pointer]:
          - img [ref=e16]
          - text: Pipeline
        - button "Contacts" [ref=e18] [cursor=pointer]:
          - img [ref=e19]
          - text: Contacts
        - button "Accounts" [ref=e23] [cursor=pointer]:
          - img [ref=e24]
          - text: Accounts
        - button "Activities" [ref=e28] [cursor=pointer]:
          - img [ref=e29]
          - text: Activities
        - button "Today" [ref=e31] [cursor=pointer]:
          - img [ref=e32]
          - text: Today
        - button "Stats" [ref=e35] [cursor=pointer]:
          - img [ref=e36]
          - text: Stats
        - button "Insights" [ref=e38] [cursor=pointer]:
          - img [ref=e39]
          - text: Insights
      - generic [ref=e42]:
        - generic [ref=e43]:
          - img [ref=e44]
          - generic [ref=e47]: Admin
          - generic [ref=e48]: admin
        - button "Sign out" [ref=e49] [cursor=pointer]:
          - img [ref=e50]
  - main [ref=e53]:
    - generic [ref=e54]:
      - heading "Pipeline" [level=1] [ref=e55]
      - button "New Deal" [ref=e56] [cursor=pointer]:
        - img [ref=e57]
        - text: New Deal
    - generic [ref=e58]:
      - generic [ref=e59]:
        - img [ref=e60]
        - text: Saved Views
      - generic [ref=e63]: No saved views
    - generic [ref=e64]:
      - generic [ref=e65]:
        - generic [ref=e66]:
          - generic [ref=e67]:
            - generic [ref=e68]: Prospecting
            - generic [ref=e69]: 0% probability
          - generic [ref=e70]: "0"
        - button "Add deal" [ref=e72] [cursor=pointer]:
          - img [ref=e73]
          - text: Add deal
      - generic [ref=e74]:
        - generic [ref=e75]:
          - generic [ref=e76]:
            - generic [ref=e77]: Qualification
            - generic [ref=e78]: 20% probability
          - generic [ref=e79]: "0"
        - button "Add deal" [ref=e81] [cursor=pointer]:
          - img [ref=e82]
          - text: Add deal
      - generic [ref=e83]:
        - generic [ref=e84]:
          - generic [ref=e85]:
            - generic [ref=e86]: Proposal
            - generic [ref=e87]: 50% probability
          - generic [ref=e88]: "0"
        - button "Add deal" [ref=e90] [cursor=pointer]:
          - img [ref=e91]
          - text: Add deal
      - generic [ref=e92]:
        - generic [ref=e93]:
          - generic [ref=e94]:
            - generic [ref=e95]: Negotiation
            - generic [ref=e96]: 75% probability
          - generic [ref=e97]: "0"
        - button "Add deal" [ref=e99] [cursor=pointer]:
          - img [ref=e100]
          - text: Add deal
      - generic [ref=e101]:
        - generic [ref=e102]:
          - generic [ref=e103]:
            - generic [ref=e104]: Closed-Won
            - generic [ref=e105]: 100% probability
          - generic [ref=e106]: "0"
        - button "Add deal" [ref=e108] [cursor=pointer]:
          - img [ref=e109]
          - text: Add deal
      - generic [ref=e110]:
        - generic [ref=e111]:
          - generic [ref=e112]:
            - generic [ref=e113]: Closed-Lost
            - generic [ref=e114]: 0% probability
          - generic [ref=e115]: "0"
        - button "Add deal" [ref=e117] [cursor=pointer]:
          - img [ref=e118]
          - text: Add deal
    - generic [ref=e120]:
      - generic [ref=e121]: Weighted Forecast
      - generic [ref=e122]: $0
      - generic [ref=e123]: open deals by stage probability
```