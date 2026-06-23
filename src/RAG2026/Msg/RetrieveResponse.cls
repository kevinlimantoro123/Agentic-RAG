/// Response from RAG2026.BO.RetrieveOperation.
Class RAG2026.Msg.RetrieveResponse Extends Ens.Response
{

/// JSON array of {label, date, text} records.
Property ResultsJSON As %String(MAXLEN = "");

}
