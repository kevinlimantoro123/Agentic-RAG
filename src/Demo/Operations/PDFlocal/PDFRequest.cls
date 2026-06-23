Class Demo.Operations.PDFlocal.PDFRequest Extends (%Persistent, Ens.Request)
{

Property KeyIndex As %Integer [ InitialExpression = 1 ];

Storage Default
{
<Data name="PDFRequestDefaultData">
<Value name="1">
<Value>%%CLASSNAME</Value>
</Value>
<Value name="2">
<Value>KeyIndex</Value>
</Value>
</Data>
<DataLocation>^Demo.OperationsC7BF.PDFRequestD</DataLocation>
<DefaultData>PDFRequestDefaultData</DefaultData>
<ExtentSize>2</ExtentSize>
<IdLocation>^Demo.OperationsC7BF.PDFRequestD</IdLocation>
<IndexLocation>^Demo.OperationsC7BF.PDFRequestI</IndexLocation>
<Property name="%%CLASSNAME">
<AverageFieldSize>2</AverageFieldSize>
<OutlierSelectivity>.999999:</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<Property name="%%ID">
<AverageFieldSize>3</AverageFieldSize>
<Selectivity>1</Selectivity>
</Property>
<Property name="KeyIndex">
<AverageFieldSize>3</AverageFieldSize>
<OutlierSelectivity>.999999:1</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<SQLMap name="IDKEY">
<BlockCount>-4</BlockCount>
</SQLMap>
<StreamLocation>^Demo.OperationsC7BF.PDFRequestS</StreamLocation>
<Type>%Storage.Persistent</Type>
}

}
