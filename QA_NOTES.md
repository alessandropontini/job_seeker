# QA Notes

## Remotive API curl evidence (HTTP 403 investigation)

### Baseline request
```bash
curl -i "https://remotive.com/api/remote-jobs?limit=1"
```

```
HTTP/1.1 200 OK
... (headers omitted for brevity)

{"00-warning": "Remotive main domain moved to remotive.com ! Please make your API calls on remotive.com/api/remote-jobs instead of remotive.io now ;)", "0-legal-notice": "Legal warning - Hey, thanks for using Remotive's API, we appreciate it! Please note that API documentation and access is granted so that developers can share our jobs further. Please do not submit Remotive jobs to third Party websites, including but not limited to: Jooble, Neuvoo, Google Jobs, LinkedIn Jobs. Please link back to the URL found on Remotive AND mention Remotive as a source in order to Remotive to get traffic from your listing. If you don't do that, we'll terminate your API access, sorry! Jobs displayed are delayed by 24 hours, the goal being that jobs are attributed to Remotive on various platforms. Displaying our jobs in order to collect signups/email addresses to show a listing constitutes a breach of our terms of services. We offer a private, paid-for API, please email us at hello(at)remotive(dot)io for more information (starting budget is $5k/mo). Please find out terms of services on https://remotive.com/api-documentation. Please note that there is absolutely no need to request Remotive Job data too frequently. Typically, you only need to GET Remotive job data through this API a couple of times a day (we advise max. 4 times a day). Our data is not changing much faster than that anyway. Note that excessive requests will be blocked. Many thanks (Rodolphe & the Remotive team!)", "job-count": 1, "total-job-count": 24, "jobs": [...]} 
```

### With explicit headers
```bash
curl -i -H "User-Agent: job_scout_integration_test/1.0" -H "Accept: application/json" "https://remotive.com/api/remote-jobs?limit=1"
```

```
HTTP/1.1 200 OK
... (headers omitted for brevity)

{"00-warning": "Remotive main domain moved to remotive.com ! Please make your API calls on remotive.com/api/remote-jobs instead of remotive.io now ;)", "0-legal-notice": "Legal warning - Hey, thanks for using Remotive's API, we appreciate it! Please note that API documentation and access is granted so that developers can share our jobs further. Please do not submit Remotive jobs to third Party websites, including but not limited to: Jooble, Neuvoo, Google Jobs, LinkedIn Jobs. Please link back to the URL found on Remotive AND mention Remotive as a source in order to Remotive to get traffic from your listing. If you don't do that, we'll terminate your API access, sorry! Jobs displayed are delayed by 24 hours, the goal being that jobs are attributed to Remotive on various platforms. Displaying our jobs in order to collect signups/email addresses to show a listing constitutes a breach of our terms of services. We offer a private, paid-for API, please email us at hello(at)remotive(dot)io for more information (starting budget is $5k/mo). Please find out terms of services on https://remotive.com/api-documentation. Please note that there is absolutely no need to request Remotive Job data too frequently. Typically, you only need to GET Remotive job data through this API a couple of times a day (we advise max. 4 times a day). Our data is not changing much faster than that anyway. Note that excessive requests will be blocked. Many thanks (Rodolphe & the Remotive team!)", "job-count": 1, "total-job-count": 24, "jobs": [...]} 
```
